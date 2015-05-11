#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

"""Create raviron SSH access keys.

Usage:
  create-key [-u <username>] [-d] <application>

The create-key commands creates a new public key that allows the user to
perform certain power control and management operations on VMs in a Ravello
application.

The key is intended to be used to as part of an OpenStack Ironic
configuration, using the "ssh" power driver

Options:
  -u, --username    The Ravello API username.
  -d, --debug       Enable debugging mode.

The Ravello API password will be read from the $RAVELLO_PASSWORD environment
variable. If it is not set, it will be prompted for if a TTY is available.
"""

from __future__ import absolute_import, print_function

import os
import sys
import docopt
import getpass
import textwrap
import subprocess
import six

from . import util
from six.moves import shlex_quote
from ravello_sdk import RavelloClient


def get_password(user):
    """Read a password, if possible."""
    passwd = os.environ.get('RAVELLO_PASSWORD')
    if passwd is None:
        if not os.isatty(sys.stdin.fileno()):
            raise RuntimeError('no TTY available, will not prompt for password')
        passwd = getpass.getpass('Enter password for {}: '.format(user))
    return passwd


def create_private_key(args, privkey):
    """Create a new private key file."""
    keycomment = 'raviron/{}/{}'.format(args['<username>'], args['<application>'])
    subprocess.check_call(['ssh-keygen', '-f', privkey, '-N', "", '-q', '-C', keycomment])


def create_proxy(args, fname):
    """Create a proxy wrapper."""
    # If running in a venv, source the same one.
    venv = os.environ.get('VIRTUAL_ENV')
    source_venv = '. {}/bin/activate'.format(venv) if venv else ''
    contents = textwrap.dedent("""\
            #!/bin/sh
            RAVELLO_USERNAME={}
            RAVELLO_PASSWORD={}
            RAVELLO_APPLICATION={}
            export RAVELLO_USERNAME RAVELLO_PASSWORD RAVELLO_APPLICATION
            {}
            python -mraviron.proxy
            """).format(shlex_quote(args['<username>']),
                        shlex_quote(args['<password>']),
                        shlex_quote(args['<application>']),
                        source_venv)
    with open(fname, 'w') as fout:
        fout.write(contents)
    util.make_executable(fname)


def add_to_authorized_keys(pubkey, command):
    """Add a public key to the authorized_keys file."""
    with open(pubkey) as fin:
        keydata = fin.read()
    sshdir = os.path.join(util.get_homedir(), '.ssh')
    authentry = 'no-pty,no-port-forwarding,no-X11-forwarding,no-agent-forwarding'
    authentry += ',command="{}" '.format(command)
    authentry += keydata
    authfile = os.path.join(sshdir, 'authorized_keys')
    with open(authfile, 'a') as fout:
        fout.write(authentry)


def _main():
    # Parse args
    args = docopt.docopt(__doc__)
    if args['--debug']:
        util.set_debug(True)
    args['<password>'] = get_password(args['<username>'])

    # Check Ravello API credentials.
    client = RavelloClient()
    client.login(args['<username>'], args['<password>'])
    app = client.get_applications(filter={'name': args['<application>']})
    if app is None:
        sys.stdout.write('Warning: app {} does not exist.\n'.format(args['<application>']))
    client.close()

    # Find out the sequence number for this new key by creating a new unique
    # public key name. We use the public key as creating the private key will
    # make ssh-keygen ask for a confirmation to overwrite it.
    sshdir = os.path.join(util.get_homedir(), '.ssh')
    util.create_directory(sshdir, 0o700)
    keytemplate = 'id_raviron_{:04}.pub'
    seqno, pubkey = util.create_unique_file_seqno(sshdir, keytemplate)

    # Create the key and add it to ~/.authorized_keys
    privkey = pubkey[:-4]
    create_private_key(args, privkey)

    bindir = os.path.join(util.get_homedir(), 'bin')
    util.create_directory(bindir, 0o755)
    proxytemplate = 'raviron-proxy-{:04}.sh'
    proxyname = os.path.join(bindir, proxytemplate.format(seqno))
    create_proxy(args, proxyname)
    add_to_authorized_keys(pubkey, proxyname)

    privbase = os.path.split(privkey)[1]
    sys.stdout.write('Private key created as: ~/.ssh/{}\n'.format(privbase))
    proxybase = os.path.split(proxyname)[1]
    sys.stdout.write('Using API proxy: ~/bin/{}\n'.format(proxybase))


def main():
    """Main wrapper function.

    Calls _main() and handles any exceptions that might occur.
    """
    try:
        _main()
    except Exception as e:
        if util.get_debug():
            raise
        sys.stdout.write('Error: {!s}\n'.format(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
