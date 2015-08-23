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

_log_dir = '/var/log/ravstack'
_log_name = 'ravstack.log'


def get_debug():
    """Return whether debugging is requested."""
    return os.environ.get('DEBUG', '0') not in ('0', 'n')

def set_debug(enabled=True):
    """Enable the $DEBUG environment variable."""
    os.environ['DEBUG'] = '1' if enabled else '0'
    update_logging_levels()


def get_verbose():
    """Enable whether verbose mode is enabled."""
    return os.environ.get('VERBOSE', '0') not in ('0', 'n')

def set_verbose(enabled=True):
    """Enable the $VERBOSE environment variable."""
    os.environ['VERBOSE'] = '1' if enabled else '0'
    update_logging_levels()


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


def get_logger():
    """Return the shared logger."""
    return logging.getLogger('ravstack')


_template = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
_ssh_template = '%(asctime)s %(levelname)s [{}] [%(name)s] %(message)s'

def setup_logging():
    """Set up logging."""
    root = logging.getLogger()
    if root.handlers:
        return
    # If running under SSH, show connection information (for debugging)
    if os.environ.get('SSH_ORIGINAL_COMMAND'):
        ssh_conn = os.environ.get('SSH_CONNECTION', '?:?')
        parts = ssh_conn.split()
        if parts[0] in ('127.0.0.1', '::1'):
            parts[0] = ''
        template = _ssh_template.format(':'.join(parts[:2]))
    else:
        template = _template
    # The stderr handler is always present, but only enabled in verbose mode.
    handler = logging.StreamHandler(sys.stderr)
    root.addHandler(handler)
    handler.setFormatter(logging.Formatter(template))
    # The logfile handlers is present only if a writable log file is available.
    logfile = get_log_file()
    if logfile:
        handler = logging.FileHandler(logfile)
        root.addHandler(handler)
        handler.setFormatter(logging.Formatter(template))
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
