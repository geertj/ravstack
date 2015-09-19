#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import sys
from . import logging, ravello, run

LOG = logging.get_logger()


def main():
    """Check a password."""

    # A password is valid if we can authenticate with it against the Ravello
    # API, and if the application we are running in is accessible to that
    # account.

    username = sys.stdin.readline()
    if not username.endswith('\n'):
        sys.exit(2)
    username = username[:-1]

    password = sys.stdin.readline()
    if not password.endswith('\n'):
        sys.exit(2)
    password = password[:-1]

    meta = ravello.get_injected_metadata()
    appid = meta.get('appId')
    if appid is None:
        LOG.error('metadata not injected, cannot check password.')
        sys.exit(3)

    client = ravello.RavelloClient()
    try:
        client.login(username, password)
        client.call('GET', '/applications/{}'.format(appid))
    except Exception as e:
        LOG.error('unable to authenticate user `{}`: {}'.format(username, e))
        sys.exit(1)

    LOG.info('successfully authenticated user `{}`.'.format(username))
    sys.exit(0)


if __name__ == '__main__':
    run.run_main(main)
