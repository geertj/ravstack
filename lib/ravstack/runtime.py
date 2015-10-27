#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import sys
import logging

from . import config, defaults, util

prog_name = __name__.split('.')[0]

LOG = logging.getLogger(prog_name)
CONF = config.Config()

DEBUG = util.EnvInt('DEBUG')
VERBOSE = util.EnvInt('VERBOSE')
LOG_STDERR = util.EnvInt('LOG_STDERR')

log_context = ''
log_datetime = '%(asctime)s '
log_template = '%(levelname)s [%(name)s] %(message)s'
log_ctx_template = '%(levelname)s [{}] [%(name)s] %(message)s'


def setup_config():
    """Return the configuration object."""
    CONF.set_schema(defaults.config_schema)
    CONF.read_file(defaults.config_file)
    CONF.update_from_env()
    meta = util.get_ravello_metadata()
    if 'appName' in meta and CONF['ravello']['application'] == '<None>':
        CONF['ravello']['application'] = meta['appName']
    CONF.update_to_env()


def setup_logging(context=None):
    """Set up or reconfigure logging."""
    root = logging.getLogger()
    if root.handlers:
        del root.handlers[:]
    global log_context
    if context is not None:
        log_context = context
    template = log_ctx_template.format(log_context) if log_context else log_template
    # Log to stderr?
    if LOG_STDERR:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(template))
        root.addHandler(handler)
    else:
        root.addHandler(logging.NullHandler())
    # Available log file?
    logfile = defaults.log_file
    if util.can_open(logfile, 'a'):
        handler = logging.FileHandler(logfile)
        handler.setFormatter(logging.Formatter(log_datetime + template))
        root.addHandler(handler)
    root.setLevel(logging.DEBUG if DEBUG else logging.INFO if VERBOSE else logging.ERROR)
    # A little less verbosity for requests.
    logger = logging.getLogger('requests.packages.urllib3.connectionpool')
    logger.setLevel(logging.DEBUG if DEBUG else logging.ERROR)
    # Silence "insecure platform" warning for requests module on Py2.7.x under
    # default verbosity.
    logging.captureWarnings(True)
    logger = logging.getLogger('py.warnings')
    logger.setLevel(logging.DEBUG if DEBUG else logging.ERROR)


# Run a main function

def run_main(func):
    """Run a main function."""

    setup_config()
    setup_logging()

    # Run the provided main function.
    try:
        func()
    except Exception as e:
        LOG.error('Uncaught exception:', exc_info=True)
        if DEBUG:
            raise
        print('Error: {!s}'.format(e))
