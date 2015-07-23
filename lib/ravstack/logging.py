#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

import os
import sys
import logging

from . import util

_log_dir = '/var/log/ravstack'
_log_name = 'ravstack.log'


def get_debug():
    """Return whether debugging is requested."""
    return os.environ.get('DEBUG', '0') not in ('0', 'n')

def set_debug(enabled=True):
    """Enable the $DEBUG environment variable."""
    os.environ['DEBUG'] = '1' if enabled else '0'


def get_verbose():
    """Enable whether verbose mode is enabled."""
    return os.environ.get('VERBOSE', '0') not in ('0', 'n')

def set_verbose(enabled=True):
    """Enable the $VERBOSE environment variable."""
    os.environ['VERBOSE'] = '1' if enabled else '0'


def get_log_file():
    """Return the log file."""
    # First try in VIRTUAL_ENV
    if 'VIRTUAL_ENV' in os.environ:
        logfile = os.path.join(os.environ['VIRTUAL_ENV'], _log_name)
        if util.can_open(logfile, 'a'):
            return logfile
    # Now try /var/log
    logfile = os.path.join(_log_dir, _log_name)
    if util.can_open(logfile, 'a'):
        return logfile


_template = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
_ssh_template = '%(asctime)s %(levelname)s [{}] [%(name)s] %(message)s'

def get_logger():
    """Set up logging."""
    root = logging.getLogger()
    logger = logging.getLogger('ravstack')
    if root.handlers:
        return logger
    # If running under SSH, show connection information (for debugging)
    if os.environ.get('SSH_ORIGINAL_COMMAND'):
        ssh_conn = os.environ.get('SSH_CONNECTION', '?:?')
        parts = ssh_conn.split()
        if parts[0] in ('127.0.0.1', '::1'):
            parts[0] = ''
        template = _ssh_template.format(':'.join(parts[:2]))
    else:
        template = _template
    if get_verbose():
        handler = logging.StreamHandler(sys.stderr)
        root.addHandler(handler)
        handler.setFormatter(logging.Formatter(template))
    logfile = get_log_file()
    if logfile:
        handler = logging.FileHandler(logfile)
        root.addHandler(handler)
        handler.setFormatter(logging.Formatter(template))
    if not root.handlers:
        handler = logging.NullHandler()
        root.addHandler(handler)
    root.setLevel(logging.DEBUG if get_debug() else logging.INFO)
    # A little less verbosity for requests.
    sublogger = logging.getLogger('requests.packages.urllib3.connectionpool')
    sublogger.setLevel(logging.DEBUG if get_debug() else logging.WARNING)
    # Silence "insecure platform" warning for requests module on Py2.7.x.
    logging.captureWarnings(True)
    sublogger = logging.getLogger('py.warnings')
    sublogger.setLevel(logging.ERROR)
    return logger
