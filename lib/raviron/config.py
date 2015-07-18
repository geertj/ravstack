#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

import os
from configparser import ConfigParser, ExtendedInterpolation


_config_name = 'raviron.conf'
_system_config = '/etc/raviron'

_default_config = [
    # section, name, default, required, description, env var, cli arg
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
    ('proxy', 'key_name', 'id_raviron', False, 'Proxy SSH keypair name.', None, None),
    ('proxy', 'proxy_name', 'raviron-proxy', False, 'Proxy SSH keypair name.', None, None),
    ('nodes', 'nodes_file', '~/instackenv.json', False,
            'Save node definition in this file.', None, '--output'),
]


def parse_config():
    """Parse configuration files."""
    config = ConfigParser(default_section='__default__',
                          interpolation=ExtendedInterpolation())
    # First splice in defaults.
    for section, name, default, *rest in _default_config:
        if section not in config:
            config.add_section(section)
        config[section][name] = default
    # Read in the config files.
    prefixes = [_system_config]
    if 'VIRTUAL_ENV' in os.environ:
        prefixes.append(os.environ['VIRTUAL_ENV'])
    config.read((os.path.join(prefix, _config_name) for prefix in prefixes))
    # Read from environment variables
    for section, name, *skip, env, cli in _default_config:
        if not env or env not in os.environ:
            continue
        config[section][name] = os.environ[env]
    return config


def update_from_args(config, args):
    """Update *config* with values specified in *args*."""
    for section, name, *skip, env, cli in _default_config:
        if args.get(cli) not in (None, False):
            config[section][name] = str(args[cli])


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


def dump_defaults():
    """Dump default configuration."""
    current = None
    for section, name, default, required, description, env, arg in _default_config:
        if section != current:
            print('[{}]'.format(section))
            current = section
        print('# {}{}'.format(description, ' [required]' if required else ''))
        if env or arg:
            env = '$' + env if env else env
            print('# Also specified as {}'.format(' or '.join(filter(None, (env, arg)))))
        print('{}{}={}\n'.format('' if required else '#', name, default))


if __name__ == '__main__':
    dump_defaults()
