#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
from configparser import ConfigParser, ExtendedInterpolation

from . import util


_config_name = 'ravstack.conf'
_system_config = '/etc/ravstack'

_default_config = [
    # section, name, default, required, description, env, arg
    ('DEFAULT', 'debug', 'False', False, 'Enable debugging.', 'DEBUG', '--debug'),
    ('DEFAULT', 'verbose', 'False', False,
            'Be verbose (shows logging on stdout).', 'VERBOSE', '--verbose'),
    ('ravello', 'username', '<None>', True,
            'Ravello API username.', 'RAVELLO_USERNAME', '--username'),
    ('ravello', 'password', '<None>', True,
            'Ravello API password.', 'RAVELLO_PASSWORD', '--password'),
    ('ravello', 'application', '<None>', False,
            'Ravello application name.', 'RAVELLO_APPLICATION', '--application'),
    ('ravello', 'pxe_iso', 'ipxe.iso', False,
            'Name of PXE boot ISO image.', None, '--pxe-iso'),
    ('ravello', 'min_runtime', '120', False,
            'Minimum application runtime (in minutes).', None, None),
    ('proxy', 'key_name', 'id_ravstack', False, 'API proxy keypair name.', None, None),
    ('proxy', 'proxy_name', 'ravstack-proxy', False, 'API proxy script.', None, None),
    ('tripleo', 'nodes_file', '~/instackenv.json', False,
            'File name containing node definitions.', None, None),
    ('tripleo', 'undercloud_env', '~/stackrc', False, 'Undercloud rc file.', None, None),
    ('tripleo', 'overcloud_env', '~/overcloudrc', False, 'Overcloud rc file.', None, None),
    ('tripleo', 'controller_name', 'controller', False,
            'Name uniquely identifying a controller node.', None, None),
    ('tripleo', 'compute_name', 'novacompute', False,
            'Name uniquely identifying a Nova compute node.', None, None),
    ('tripleo', 'ssh_user', 'heat-admin', False,
            'Name for ssh user to login to nodes.', None, None),
]


def parse_config():
    """Parse configuration files."""
    config = ConfigParser(default_section='__default__',
                          interpolation=ExtendedInterpolation())
    # First splice in defaults.
    for section, name, default, req, desc, env, arg in _default_config:
        if section not in config:
            config.add_section(section)
        config[section][name] = default
    # Read in the config files.
    prefixes = [_system_config]
    if 'VIRTUAL_ENV' in os.environ:
        prefixes.append(os.environ['VIRTUAL_ENV'])
    config.read((os.path.join(prefix, _config_name) for prefix in prefixes))
    # Read from environment variables
    for section, name, default, req, desc, env, arg in _default_config:
        if not env or env not in os.environ:
            continue
        config[section][name] = os.environ[env]
    return config


def update_from_args(config, args):
    """Update *config* with values specified in *args*."""
    for section, name, default, req, desc, env, arg in _default_config:
        if args.get(arg) not in (None, False):
            config[section][name] = str(args[arg])


def require(config, section, key):
    """Require section/key to be part of config, raise otherwise."""
    if section not in config:
        raise RuntimeError('No such configuration section: {}'.format(section))
    cfgsect = config[section]
    if key not in cfgsect or cfgsect[key] == '<None>':
        message = 'Config `[{}]{}` not set.'.format(section, key)
        locations = []
        for item in _default_config:
            if item[0] == section and item[1] == key:
                if item[-2]:
                    locations.append('$' + item[-2])
                if item[-1]:
                    locations.append(item[-1])
                break
        if locations:
            message += ' Also available as {}.'.format(' or '.join((locations)))
        raise RuntimeError(message)
    return cfgsect[key]


def dump_defaults(fout):
    """Dump default configuration."""
    current = None
    for section, name, default, required, description, env, arg in _default_config:
        if section != current:
            fout.write('[{}]\n'.format(section))
            current = section
        fout.write('# {}{}\n'.format(description, ' [required]' if required else ''))
        if env or arg:
            env = '$' + env if env else env
            fout.write('# Also specified as {}\n'.format(' or '.join(filter(None, (env, arg)))))
        fout.write('{}{}={}\n\n'.format('' if required else '#', name, default))


def do_create(env):
    """The 'ravstack config-create` command."""
    if 'VIRTUAL_ENV' in os.environ:
        cfgname = os.path.join(os.environ['VIRTUAL_ENV'], _config_name)
    else:
        st = util.try_stat(_system_config)
        if st is None:
            util.create_directory(_system_config)
        cfgname = os.path.join(_system_config, _config_name)
    st = util.try_stat(cfgname)
    if st is not None:
        return
    with open(cfgname, 'w') as fout:
        dump_defaults(fout)
    print('Created config file `{}`.'.format(cfgname))
