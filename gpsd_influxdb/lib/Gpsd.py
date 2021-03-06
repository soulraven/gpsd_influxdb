#  -*- coding: utf-8 -*-
#              Copyright (C) 2018-2021 ProGeek
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.


import logging

import socket
import json
import datetime

logger = logging.getLogger(__name__)


class NoFixError(Exception):

    def __init__(self, reason):
        self.reason = reason


class Gpsd(object):
    """ Class representing geo information returned by GPSD
        Use the attributes to get the raw gpsd data, use the methods to get parsed and corrected information.
        :type mode: int
        :type sats: int
        :type sats_valid: int
        :type lon: float
        :type lat: float
        :type alt: float
        :type track: float
        :type hspeed: float
        :type climb: float
        :type time: str
        :type error: dict[str, float]
        :var self.mode: Indicates the status of the GPS reception, 0=No value, 1=No fix, 2=2D fix, 3=3D fix
        :var self.sats: The number of satellites received by the GPS unit
        :var self.sats_valid: The number of satellites with valid information
        :var self.lon: Longitude in degrees
        :var self.lat: Latitude in degrees
        :var self.alt: Altitude in meters
        :var self.track: Course over ground, degrees from true north
        :var self.hspeed: Speed over ground, meters per second
        :var self.climb: Climb (positive) or sink (negative) rate, meters per second
        :var self.time: Time/date stamp in ISO8601 format, UTC. May have a fractional part of up to .001sec precision.
        :var self.error: GPSD error margin information
        GPSD error margin information
        -----------------------------
        c: ecp: Climb/sink error estimate in meters/sec, 95% confidence.
        s: eps: Speed error estimate in meters/sec, 95% confidence.
        t: ept: Estimated timestamp error (%f, seconds, 95% confidence).
        v: epv: Estimated vertical error in meters, 95% confidence. Present if mode is 3 and DOPs can be
                calculated from the satellite view.
        x: epx: Longitude error estimate in meters, 95% confidence. Present if mode is 2 or 3 and DOPs
                can be calculated from the satellite view.
        y: epy: Latitude error estimate in meters, 95% confidence. Present if mode is 2 or 3 and DOPs can
                be calculated from the satellite view.
        """

    state = {}
    gpsTimeFormat = '%Y-%m-%dT%H:%M:%S.%fZ'
    gpsd_socket = None
    gpsd_stream = None

    modes = {
        0: 'No mode',
        1: 'No fix',
        2: '2D fix',
        3: '3D fix'
    }

    def __init__(self, host="127.0.0.1", port=2947):
        self.mode = 0
        self.sats = 0
        self.sats_valid = 0
        self.hdop = 0
        self.pdop = 0
        self.lon = 0.0
        self.lat = 0.0
        self.alt = 0.0
        self.track = 0
        self.hspeed = 0
        self.climb = 0
        self.time = ''
        self.error = {}

        self.connect(host, port)

    def __repr__(self):

        if self.mode < 2:
            return "<Gpsd {}>".format(self.modes[self.mode])
        if self.mode == 2:
            return "<Gpsd 2D Fix {} {}>".format(self.lat, self.lon)
        if self.mode == 3:
            return "<Gpsd 3D Fix {} {} ({} m)>".format(self.lat, self.lon, self.alt)

    @classmethod
    def from_json(cls, packet):
        """ Create GpsResponse instance based on the json data from GPSD
        :type packet: dict
        :param packet: JSON decoded GPSD response
        :return: GpsResponse
        """
        result = cls()
        if not packet['active']:
            raise UserWarning('GPS not active')
        last_tpv = packet['tpv'][-1]
        last_sky = packet['sky'][-1]

        if 'satellites' in last_sky:
            result.sats = len(last_sky['satellites'])
            result.sats_valid = len(
                [sat for sat in last_sky['satellites'] if sat['used']])
        else:
            result.sats = 0
            result.sats_valid = 0

        result.hdop = last_sky['hdop'] if 'hdop' in last_sky else 0.0
        result.vdop = last_sky['vdop'] if 'vdop' in last_sky else 0.0
        result.pdop = last_sky['pdop'] if 'pdop' in last_sky else 0.0

        result.mode = last_tpv['mode']

        if last_tpv['mode'] >= 2:
            result.lon = last_tpv['lon'] if 'lon' in last_tpv else 0.0
            result.lat = last_tpv['lat'] if 'lat' in last_tpv else 0.0
            result.track = last_tpv['track'] if 'track' in last_tpv else 0
            result.hspeed = last_tpv['speed'] if 'speed' in last_tpv else 0
            result.time = last_tpv['time'] if 'time' in last_tpv else ''
            result.error = {
                # Estimated climb error in meters per second. Certainty unknown.
                'c': 0,
                # Ground speed uncertainty (meters/second) [eps]
                's': last_tpv['eps'] if 'eps' in last_tpv else 0,
                # Temporal uncertainty [ept]
                't': last_tpv['ept'] if 'ept' in last_tpv else 0,
                'v': 0,
                # Longitude error estimate in meters. Certainty unknown.
                'x': last_tpv['epx'] if 'epx' in last_tpv else 0,
                # Latitude error estimate in meters. Certainty unknown.
                'y': last_tpv['epy'] if 'epy' in last_tpv else 0
            }

        if last_tpv['mode'] >= 3:
            result.alt = last_tpv['alt'] if 'alt' in last_tpv else 0.0
            result.climb = last_tpv['climb'] if 'climb' in last_tpv else 0
            # Estimated climb error in meters per second. Certainty unknown.
            result.error['c'] = last_tpv['epc'] if 'epc' in last_tpv else 0
            # Estimated vertical error in meters. Certainty unknown.
            result.error['v'] = last_tpv['epv'] if 'epv' in last_tpv else 0

        return result

    def connect(self, host, port):
        """ Connect to a GPSD instance
        :param host: hostname for the GPSD server
        :param port: port for the GPSD server
        """
        if self.gpsd_socket or self.gpsd_stream:
            self.disconnect()
            print('get disconnect')
            logger.debug('Previous connection detected. Reconnecting')

        logger.debug("Connecting to gpsd socket at {}:{}".format(host, port))
        self.gpsd_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.gpsd_socket.connect((host, port))
        self.gpsd_stream = self.gpsd_socket.makefile(mode="rw")
        logger.debug("Waiting for welcome message")
        welcome_raw = self.gpsd_stream.readline()
        welcome = json.loads(welcome_raw)
        if welcome['class'] != "VERSION":
            raise Exception(
                "Unexpected data received as welcome. Is the server a gpsd 3 server?")
        logger.debug("Enabling gps")
        self.gpsd_stream.write('?WATCH={"enable":true}\n')
        self.gpsd_stream.flush()

        for i in range(0, 2):
            raw = self.gpsd_stream.readline()
            parsed = json.loads(raw)
            self._parse_state_packet(parsed)

    def disconnect(self):
        """ Disconnect to a GPSD
        """
        logger.debug('Disconnecting')
        if self.gpsd_socket:
            self.gpsd_socket.shutdown(socket.SHUT_RDWR)
            self.gpsd_socket.close()
            self.gpsd_socket = None
        if self.gpsd_stream:
            self.gpsd_stream.close()
            self.gpsd_stream = None
        self.state = {}

    def _parse_state_packet(self, json_data):
        if json_data['class'] == 'DEVICES':
            if not json_data['devices']:
                logger.warning('No gps devices found')
            self.state['devices'] = json_data
        elif json_data['class'] == 'WATCH':
            self.state['watch'] = json_data
        else:
            raise Exception(
                "Unexpected message received from gps: {}".format(json_data['class']))

    def get_current(self):
        """ Poll gpsd for a new position
        :return: GpsResponse
        """
        logger.debug("Polling gps")
        self.gpsd_stream.write("?POLL;\n")
        self.gpsd_stream.flush()
        raw = self.gpsd_stream.readline()
        response = json.loads(raw)
        if response['class'] != 'POLL':
            raise Exception(
                "Unexpected message received from gps: {}".format(response['class']))
        return Gpsd.from_json(response)

    def position(self):
        """ Get the latitude and longtitude as tuple.
        Needs at least 2D fix.
        :return: (float, float)
        """
        if self.mode < 2:
            raise NoFixError("Needs at least 2D fix")
        return self.lat, self.lon

    def altitude(self):
        """ Get the altitude in meters.
        Needs 3D fix
        :return: (float)
        """
        if self.mode < 3:
            raise NoFixError("Needs at least 3D fix")
        return self.alt

    def movement(self):
        """ Get the speed and direction of the current movement as dict
        The speed is the horizontal speed.
        The climb is the vertical speed
        The track is te direction of the motion
        Needs at least 3D fix
        :return: dict[str, float]
        """
        if self.mode < 3:
            raise NoFixError("Needs at least 3D fix")
        return {"speed": self.hspeed, "track": self.track, "climb": self.climb}

    def speed_vertical(self):
        """ Get the vertical speed with the small movements filtered out.
        Needs at least 2D fix
        :return: float
        """
        if self.mode < 2:
            raise NoFixError("Needs at least 2D fix")
        if abs(self.climb) < self.error['c']:
            return 0
        else:
            return self.climb

    def speed(self):
        """ Get the horizontal speed with the small movements filtered out.
        Needs at least 2D fix
        :return: float
        """
        if self.mode < 2:
            raise NoFixError("Needs at least 2D fix")
        if self.hspeed < self.error['s']:
            return 0
        else:
            return self.hspeed

    def position_precision(self):
        """ Get the error margin in meters for the current fix.
        The first value return is the horizontal error, the second
        is the vertical error if a 3D fix is available
        Needs at least 2D fix
        :return: (float, float)
        """
        if self.mode < 2:
            raise NoFixError("Needs at least 2D fix")
        return max(self.error['x'], self.error['y']), self.error['v']

    def map_url(self):
        """ Get a openstreetmap url for the current position
        :return: str
        """
        if self.mode < 2:
            raise NoFixError("Needs at least 2D fix")
        return "https://www.openstreetmap.org/?mlat={}&mlon={}&zoom=15".format(self.lat, self.lon)

    def get_time(self, local_time=False):
        """ Get the GPS time
        :type local_time: bool
        :param local_time: Return date in the local timezone instead of UTC
        :return: datetime.datetime
        """
        if self.mode < 2:
            raise NoFixError("Needs at least 2D fix")
        time = datetime.datetime.strptime(self.time, self.gpsTimeFormat)

        if local_time:
            time = time.replace(tzinfo=datetime.timezone.utc).astimezone()

        return time

    def get_mode(self):
        if self.mode < 2:
            return "{}".format(self.modes[self.mode])
        if self.mode == 2:
            return "2D Fix"
        if self.mode == 3:
            return "3D Fix"

    def device(self):
        """ Get information about current gps device
        :return: dict
        """
        return {
            'path': self.state['devices']['devices'][0]['path'],
            'speed': self.state['devices']['devices'][0]['bps'],
            'driver': self.state['devices']['devices'][0]['driver']
        }
