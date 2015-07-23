#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

import json
import copy

from . import ravello, config, logging, util


class Environment:
    """Environment used to pass per invocation variables."""

    def __init__(self):
        self._lazy = {}

    def lazy_attr(self, name, factory):
        self._lazy[name] = factory

    def __getattr__(self, name):
        if name not in self._lazy:
            raise AttributeError('no such attribute: {!r}'.format(name))
        setattr(self, name, self._lazy[name]())
        return getattr(self, name)


def update_from_ravello_config(cfg):
    """Update configuration from Ravello configuration in /etc/ravello/vm.json."""
    try:
        with open('/etc/ravello/vm.json') as fin:
            meta = json.loads(fin.read())
    except IOError:
        return
    if cfg['ravello']['application'] == '<None>':
        cfg['ravello']['application'] = meta['appName']


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
        raise RuntimeError('Application `{}` not found'.format(name))
    app = env.client.call('GET', '/applications/{id}'.format(**apps[0]))
    return app


def get_nodes(app):
    """Return the "nodes" from a Ravello application.

    The list contains all VMs with static networking, and is sorted on
    increasing IP on the first index.  The Ironic controller node will be the
    first in the list, and will be followed by the managed nodes.
    """
    nodes = []
    for vm in ravello.get_vms(app):
        if not vm.get('networkConnections'):
            continue
        node = copy.deepcopy(vm)
        node['networkConnections'].sort(key=lambda c: c['device']['index'])
        all_static = True
        for conn in node['networkConnections']:
            scfg = conn.get('ipConfig', {}).get('staticIpConfig', {})
            if 'ip' not in scfg or 'mask' not in scfg:
                all_static = False
                break
        if all_static:
            nodes.append(node)
    nodes.sort(key=lambda vm: util.inet_aton(vm['networkConnections'][0]
                                               ['ipConfig']['staticIpConfig']['ip']))
    return nodes


def get_pxe_iso(env):
    """Return the disk image for the PXE boot iso."""
    name = config.require(env.config, 'ravello', 'pxe_iso')
    images = env.client.call('GET', '/diskImages')
    for image in images:
        if image['name'] == name:
            return image
    raise RuntimeError('PXE ISO `{}` not found.'.format(name))


def get_env_under(env):
    """Return the parsed environment file for the undercloud."""
    fname = env.config['tripleo']['undercloud_env']
    return util.parse_env_file(fname, '^OS_|_VERSION=')


def get_env_over(env):
    """Return the parsed environment file for the overcloud."""
    fname = env.config['tripleo']['overcloud_env']
    return util.parse_env_file(fname, '^OS_|_VERSION=')


def get_keystone_client(env):
    """Return a nova client based on *env*."""
    from keystoneclient.v2_0 import client
    client = client.Client(auth_url=env['OS_AUTH_URL'],
                           username=env['OS_USERNAME'],
                           password=env['OS_PASSWORD'],
                           tenant_name=env['OS_TENANT_NAME'])
    return client


def get_nova_client(env):
    """Return a nova client based on *env*."""
    from novaclient.v2 import client
    client = client.Client(auth_url=env['OS_AUTH_URL'],
                           username=env['OS_USERNAME'],
                           api_key=env['OS_PASSWORD'],
                           project_id=env['OS_TENANT_NAME'])
    return client


def get_environ(args=None):
    """Construct an "environment" that provides the common requirements used by
    the different commands."""
    if args is None:
        args = {}
    env = Environment()
    cfg = config.parse_config()
    config.update_from_args(cfg, args)
    update_from_ravello_config(cfg)
    if cfg['DEFAULT'].getboolean('debug'):
        logging.set_debug()
    if cfg['DEFAULT'].getboolean('verbose'):
        logging.set_verbose()
    env.logger = logging.get_logger()
    env.config = cfg
    env.args = args
    env.lazy_attr('client', lambda: get_ravello_client(env))
    env.lazy_attr('application', lambda: get_ravello_application(env))
    env.lazy_attr('nodes', lambda: get_nodes(env.application))
    env.lazy_attr('iso', lambda: get_pxe_iso(env))
    env.lazy_attr('env_under', lambda: get_env_under(env))
    env.lazy_attr('env_over', lambda: get_env_over(env))
    env.lazy_attr('nova_under', lambda: get_nova_client(env.env_under))
    env.lazy_attr('keystone_over', lambda: get_keystone_client(env.env_over))
    return env
