#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import sys
import json
import logging

from . import ravello, util, runtime, defaults
from .runtime import LOG


def main():
    """Check a password."""

    # We support two ways of validating a password:
    #
    # - If the username is "admin", the password is checked against the
    #   per-instance password in /var/run/ravstack. Per-instance means that the
    #   password is only valid under the current CloudInit instance, and is
    #   regenerated if the instance changes. This closes a security hole where
    #   static passwords could become embedded in a Ravello blueprint.
    #
    # - If the username is not "admin", the password is checked against the
    #   Ravello API. This also prevents the issue where a static passwords gets
    #   embedded into a blueprint. However, if you are preparing a public
    #   appliance, do not use this technique as the password is cached on disk
    #   by the default mod_authnz_external configuration in share/.

    username = sys.stdin.readline()
    if not username.endswith('\n'):
        sys.exit(2)
    username = username[:-1]

    password = sys.stdin.readline()
    if not password.endswith('\n'):
        sys.exit(2)
    password = password[:-1]

    if username == 'admin':
        instance = util.get_cloudinit_instance()
        if not instance:
            LOG.error('no cloudinit instance, cannot use `admin` user.')
            sys.exit(1)
        with open(defaults.password_file) as fin:
            pwdata = json.loads(fin.read())
        if instance not in pwdata:
            LOG.error('instance not configured in password file.')
            sys.exit(1)
        if util.constant_time_strcmp(password, pwdata[instance]):
            LOG.error('unable to authenticate user `{}`.'.format(username))
            sys.exit(1)

    else:
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
    runtime.run_main(main)
