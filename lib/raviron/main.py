#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

"""Ravello Ironic command-line utility.

Usage:
  raviron [options] proxy-create
  raviron [options] proxy-run
  raviron [options] node-create [-c <cpus>] [-m <memory>] [-D <disk>]
                                [-n <network>]...
  raviron [options] node-sync [-o <file>]
  raviron --help

Command help:
  proxy-create      Create SSH->Ravello API proxy.
  proxy-run         Run the API proxy.
  node-create       Create a new node, add it to `~/nodes.json`.
  node-sync         Sync all nodes to `~/nodes.json`.

Options:
  -d, --debug       Enable debugging.
  -v, --verbose     Be verbose (shows logging output on stdout)
  -u <username>, --username=<username>
                    Ravello API username.
  -p <password>, --password=<password>
                    Ravello API password.
  -a <application>, --application=<application>
                    The Ravello application name.

Options for `node-create`:
  -c <cpus>, --cpus=<cpus>
                    The number of CPUs. [default: 2]
  -m <memory>, --memory=<memory>
                    The amount of memory in MB. [default: 8192]
  -D <disk>, --disk=<disk>
                    The size of the disk in GB. [default: 60]
  -n <network>, --network=<network>
                    Network specification. Use the following format:
                    ethX,ip/mask[,gateway[,dns]]

Options for `node-sync`:
  -o <file>, --output=<file>
                    Save node definition to this file.
"""

import sys
import docopt

from . import proxy, node, logging, factory


def _main():
    """Raviron main entry point."""
    args = docopt.docopt(__doc__)
    env = factory.get_environ(args)

    if args['proxy-create']:
        proxy.create_main(env)
    elif args['proxy-run']:
        proxy.run_main(env)
    elif args['node-create']:
        node.create_main(env)
    elif args['node-sync']:
        node.sync_main(env)


def main():
    """Main wrapper function. Calls _main() and handles exceptions."""
    try:
        _main()
    except Exception as e:
        log = logging.get_logger()
        log.error('Uncaught exception:', exc_info=True)
        if logging.get_debug():
            raise
        sys.stdout.write('Error: {!s}\n'.format(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
