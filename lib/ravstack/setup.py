#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
import json
import binascii

from . import util, defaults
from .runtime import CONF


def do_setup(env):
    """The 'ravstack setup` command."""

    # Create default config file and directory.
    cfgname = defaults.config_file
    cfgdir, _ = os.path.split(cfgname)
    st = util.try_stat(cfgdir)
    if st is None:
        util.create_directory(cfgdir)
    st = util.try_stat(cfgname)
    if st is None:
        util.create_file(cfgname)
        with open(cfgname, 'w') as fout:
            CONF.write_defaults(fout)
        print('Created config file `{}`.'.format(cfgname))

    # Create log file and directory.
    logname = defaults.log_file
    logdir, _ = os.path.split(logname)
    st = util.try_stat(logdir)
    if st is None:
        util.create_directory(logdir)
    st = util.try_stat(logname)
    if st is None:
        util.create_file(logname)
        print('Created log file `{}`.'.format(logname))

    # Create runtime directory and per-instance unique password.
    pwname = defaults.password_file
    rtdir, _ = os.path.split(pwname)
    st = util.try_stat(rtdir)
    if st is None:
        util.create_directory(rtdir)
        print('Created runtime directory `{}`.'.format(rtdir))
    instance = util.get_cloudinit_instance() or 'unset'
    if instance:
        st = util.try_stat(pwname)
        if st:
            with open(pwname) as fin:
                pwdata = json.loads(fin.read())
        else:
            pwdata = {}
        if instance not in pwdata:
            pwdata[instance] = binascii.hexlify(os.urandom(12)).decode('ascii')
            with open(pwname, 'w') as fout:
                fout.write(json.dumps(pwdata, sort_keys=True, indent=2))
                fout.write('\n')
            print('Created per-instance password file `{}`.'.format(pwname))
