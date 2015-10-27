#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
from collections import namedtuple
from configparser import ConfigParser, ExtendedInterpolation


CI = namedtuple('ConfigItem', ('section', 'name', 'default',
                               'required', 'description', 'env', 'arg'))

class Config(ConfigParser):
    """Configuration object."""

    def __init__(self):
        super(Config, self).__init__(interpolation=ExtendedInterpolation())
        self.schema = []

    def set_schema(self, schema):
        """Splice in default configuration items from *defaults*."""
        for ci in schema:
            if not ci.default:
                continue
            if ci.section not in self:
                self.add_section(ci.section)
            if ci.name not in self[ci.section]:
                self[ci.section][ci.name] = ci.default
        self.schema = schema

    def read_file(self, config_file):
        """Read settings from *config_file*."""
        super(Config, self).read(config_file)

    def update_from_args(self, args):
        """Update the configuration object from command line arguments."""
        for ci in self.schema:
            if args.get(ci.arg) in (None, False):
                continue
            if ci.section not in self:
                self.add_section(ci.section)
            self[ci.section][ci.name] = str(args[ci.arg])

    def update_from_env(self):
        """Update the configuration object from environment variables."""
        for ci in self.schema:
            if not ci.env or ci.env not in os.environ:
                continue
            if ci.section not in self:
                self.add_section(ci.section)
            self[ci.section][ci.name] = os.environ[ci.env]

    def update_to_env(self):
        """Update the environment with update config items."""
        for ci in self.schema:
            if not ci.env:
                continue
            value = self.get(ci.section, ci.name, fallback='<None>')
            if value != os.environ.get(ci.env, '<None>'):
                os.environ[ci.env] = value

    def require(self, section, key):
        """Require section/key to be part of config, raise otherwise."""
        if section not in self:
            raise RuntimeError('No such configuration section: {}'.format(section))
        cfgsect = self[section]
        if key not in cfgsect or cfgsect[key] == '<None>':
            message = 'Config `[{}]{}` not set.'.format(section, key)
            locations = []
            for item in self.schema:
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

    def write_defaults(self, fout):
        """Write out the default configuration."""
        section = None
        for ci in self.schema:
            if ci.section != section:
                fout.write('[{}]\n'.format(ci.section))
                section = ci.section
            fout.write('# {}{}\n'.format(ci.description, ' [required]' if ci.required else ''))
            altlocs = []
            if ci.env:
                altlocs.append('$' + ci.env)
            if ci.arg:
                altlocs.append(ci.arg)
            if altlocs:
                fout.write('# Also specified as {}\n'.format(' or '.join(altlocs)))
            fout.write('{}{}={}\n\n'.format('' if ci.required else '#', ci.name, ci.default))
