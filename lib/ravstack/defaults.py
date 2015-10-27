#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
from .config import CI


prog_name = __name__.split('.')[0]

def redirect(dirname, template=None):
    if 'VIRTUAL_ENV' in os.environ:
        dirname = os.environ['VIRTUAL_ENV']
    else:
        dirname = dirname.format(prog_name=prog_name)
    if 'DESTDIR' in os.environ:
        dirname = os.path.join(os.environ['DESTDIR'], dirname)
    if template is None:
        return dirname
    return os.path.join(dirname, template.format(prog_name=prog_name))

config_file = redirect('/etc/{prog_name}', '{prog_name}.conf')
log_file = redirect('/var/log/{prog_name}', '{prog_name}.log')
password_file = redirect('/var/run/{prog_name}', 'passwords.json')


config_schema = [
    # section, name, default, required, description, env, arg
    CI(prog_name, 'debug', 'False', False, 'Enable debugging.', 'DEBUG', '--debug'),
    CI(prog_name, 'verbose', 'False', False, 'Be verbose.', 'VERBOSE', '--verbose'),
    CI(prog_name, 'log_stderr', 'False', False, 'Log to stderr.', 'LOG_STDERR', '--log-stderr'),
    CI('ravello', 'username', '<None>', True,
            'Ravello API username.', 'RAVELLO_USERNAME', '--username'),
    CI('ravello', 'password', '<None>', True,
            'Ravello API password.', 'RAVELLO_PASSWORD', '--password'),
    CI('ravello', 'application', '<None>', False,
            'Ravello application name.', 'RAVELLO_APPLICATION', '--application'),
    CI('ravello', 'pxe_iso', 'ipxe.iso', False,
            'Name of PXE boot ISO image.', None, '--pxe-iso'),
    CI('ravello', 'min_runtime', '120', False,
            'Minimum application runtime (in minutes).', None, None),
    CI('proxy', 'key_name', 'id_ravstack', False, 'API proxy keypair name.', None, None),
    CI('proxy', 'proxy_name', 'ravstack-proxy', False, 'API proxy script.', None, None),
    CI('tripleo', 'nodes_file', '~/instackenv.json', False,
            'File name containing node definitions.', None, None),
    CI('tripleo', 'undercloud_env', '~/stackrc', False, 'Undercloud rc file.', None, None),
    CI('tripleo', 'overcloud_env', '~/overcloudrc', False, 'Overcloud rc file.', None, None),
    CI('tripleo', 'controller_name', 'controller', False,
            'Name uniquely identifying a controller node.', None, None),
    CI('tripleo', 'compute_name', 'novacompute', False,
            'Name uniquely identifying a Nova compute node.', None, None),
    CI('tripleo', 'ssh_user', 'heat-admin', False,
            'Name for ssh user to login to nodes.', None, None),
]
