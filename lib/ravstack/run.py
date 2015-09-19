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

from . import logging

LOG = logging.get_logger()


def run_main(func):
    """Run a main function."""
    # Initialize logging
    logging.setup_logging()

    # If running under SSH, show it in the logging context
    if os.environ.get('SSH_ORIGINAL_COMMAND'):
        ssh_conn = os.environ.get('SSH_CONNECTION', '?:?')
        parts = ssh_conn.split()
        if parts[0] in ('127.0.0.1', '::1'):
            parts[0] = ''
        context = ':'.join(parts[:2])
        logging.set_log_context(context)

    # Run the provided main function.
    try:
        func()
    except Exception as e:
        LOG.error('Uncaught exception:', exc_info=True)
        if logging.get_debug() and not logging.get_verbose():
            raise
        sys.stdout.write('Error: {!s}\n'.format(e))
        sys.exit(1)
