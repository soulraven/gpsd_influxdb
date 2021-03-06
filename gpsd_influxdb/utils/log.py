#  -*- coding: utf-8 -*-
#
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


import os
from pathlib import Path
import logging
import logging.config

from gpsd_influxdb.conf import settings
from gpsd_influxdb.utils.utils import import_string

DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'gpsd_influxdb.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'gpsd_influxdb.utils.log.RequireDebugTrue',
        }
    },
    'formatters': {
        'cf_ddns.server': {
            '()': 'gpsd_influxdb.utils.log.ServerFormatter',
            'format': '[{server_time}] {message}',
            'style': '{',
        },
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 3,
            'filename': 'log/debug.log',
            'formatter': 'verbose',
            'filters': ['require_debug_true']
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        'gpsd_logging': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'file': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': False,

        },
        'schedule': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        }
    }
}


def configure_logging(logging_config, logging_settings):
    if logging_config:
        # First find the logging configuration function ...
        logging_config_func = import_string(logging_config)

        logging.config.dictConfig(DEFAULT_LOGGING)

        # ... then invoke it with the logging settings
        if logging_settings:
            logging_config_func(logging_settings)


class RequireDebugFalse(logging.Filter):

    def filter(self, records):
        return not settings.DEBUG


class RequireDebugTrue(logging.Filter):

    def filter(self, record):
        return settings.DEBUG


class ServerFormatter(logging.Formatter):
    default_time_format = '%d/%b/%Y %H:%M:%S'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record):

        if self.uses_server_time() and not hasattr(record, 'server_time'):
            record.server_time = self.formatTime(record, self.datefmt)

        return super().format(record)

    def uses_server_time(self):
        return self._fmt.find('{server_time}') >= 0
