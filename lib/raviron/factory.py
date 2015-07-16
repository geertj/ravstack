#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

import json
from . import ravello, config, logging


class Environment:
    """Environment used to pass per invocation variables."""


def get_ravello_client(env):
    """Return a API client connection."""
    username = config.require(env.config, 'ravello', 'username')
    password = config.require(env.config, 'ravello', 'password')
    client = ravello.RavelloApi()
    try:
        client.login(username, password)
    except ravello.HTTPError:
        if logging.get_debug():
            raise
        raise RuntimeError('login failed with provided credentials')
    log = logging.get_logger()
    log.debug('logged in as `{}`'.format(username))
    log.debug('member of organization `{}`'.format(client.user_info
                        .get('organizationProfile', {}).get('organizationName', '')))
    return client


def get_ravello_application(env):
    """Return the Ravello application we're working in."""
    name = config.require(env.config, 'ravello', 'application')
    apps = env.client.call('POST', '/applications/filter', ravello.simple_filter(name=name))
    if len(apps) == 0:
        raise RuntimeError('application {} not found'.format(name))
    app = env.client.call('GET', '/applications/{id}'.format(**apps[0]))
    return app


def update_from_ravello_config(cfg):
    """Update configuration from Ravello configuration in /etc/ravello/vm.json."""
    try:
        with open('/etc/ravello/vm.json') as fin:
            meta = json.loads(fin.read())
    except IOError:
        return
    if cfg['ravello']['application'] == '<None>':
        cfg['ravello']['application'] = meta['appName']


def get_environ(args=None):
    """Construct an "environment" that provides the common requirements used by
    the different commands."""
    if args is None:
        args = {}
    env = Environment()
    cfg = config.parse_config()
    config.update_from_args(cfg, args)
    update_from_ravello_config(cfg)
    env.config = cfg
    env.args = args
    if args['--debug']:
        logging.set_debug()
    if args['--verbose']:
        logging.set_verbose()
    env.logger = logging.get_logger()
    env.client = get_ravello_client(env)
    env.application = get_ravello_application(env)
    return env
