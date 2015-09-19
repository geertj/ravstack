#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
import sys
import logging

from . import util

_log_name = __name__.split('.')[0]
_log_dir = '/var/log/{}'.format(_log_name)
_log_file = '{}.log'.format(_log_name)
_log_template = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
_log_ctx_template = '%(asctime)s %(levelname)s [{}] [%(name)s] %(message)s'


def get_logger():
    """Return the shared logger."""
    return logging.getLogger(_log_name)


class EnvBool(object):
    """Object is true or not depending on the value of an environment
    variable."""

    def __init__(self, name, default='0'):
        self._name = name
        self._default = default

    def __nonzero__(self):
        value = os.environ.get(self._name, '')
        if value in ('n', 'no'):
            value = '0'
        elif value in ('y', 'yes'):
            value = '1'
        elif not value.isdigit():
            value = self._default
        return int(value)

    __bool__ = __nonzero__


def get_debug():
    """Return whether debugging is requested."""
    return EnvBool('DEBUG')

def set_debug(enabled=True):
    """Enable the $DEBUG environment variable."""
    os.environ['DEBUG'] = '1' if enabled else '0'
    update_logging_levels()


def get_verbose():
    """Enable whether verbose mode is enabled."""
    return EnvBool('VERBOSE')

def set_verbose(enabled=True):
    """Enable the $VERBOSE environment variable."""
    os.environ['VERBOSE'] = '1' if enabled else '0'
    update_logging_levels()


def get_log_file():
    """Return the log file."""
    # First try in VIRTUAL_ENV
    if 'VIRTUAL_ENV' in os.environ:
        logfile = os.path.join(os.environ['VIRTUAL_ENV'], _log_file)
        if util.can_open(logfile, 'a'):
            return logfile
    # Now try /var/log
    logfile = os.path.join(_log_dir, _log_file)
    if util.can_open(logfile, 'a'):
        return logfile


def set_log_context(context):
    """Set up a logging context."""
    root = logging.getLogger()
    template = _log_ctx_template.format(context)
    for handler in root.handlers:
        handler.setFormatter(logging.Formatter(template))


def setup_logging():
    """Set up logging."""
    root = logging.getLogger()
    if root.handlers:
        return
    # The stderr handler is always present, but only enabled in verbose mode.
    handler = logging.StreamHandler(sys.stderr)
    root.addHandler(handler)
    handler.setFormatter(logging.Formatter(_log_template))
    # The logfile handlers is present only if a writable log file is available.
    logfile = get_log_file()
    if logfile:
        handler = logging.FileHandler(logfile)
        root.addHandler(handler)
        handler.setFormatter(logging.Formatter(_log_template))
    update_logging_levels()


def update_logging_levels():
    """Update loging levels based on $DEBUG and $VERBOSE."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if get_debug() else logging.INFO)
    # The stdout handler.
    handler = root.handlers[0]
    handler.setLevel(logging.DEBUG if get_verbose() else logging.CRITICAL)
    # A little less verbosity for requests.
    logger = logging.getLogger('requests.packages.urllib3.connectionpool')
    logger.setLevel(logging.DEBUG if get_debug() else logging.WARNING)
    # Silence "insecure platform" warning for requests module on Py2.7.x.
    logging.captureWarnings(True)
    logger = logging.getLogger('py.warnings')
    logger.setLevel(logging.ERROR)
