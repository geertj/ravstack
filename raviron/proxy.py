#
# This file is part of raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the raviron authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import re
import os
import sys
import json

from ravello_sdk import RavelloClient
from . import util


@util.memoize
def get_ravello_metadata():
    """Get Ravello metadata from /etc/ravello/vm.json.

    Returns the parsed JSON as a dictionary, or None if the Ravello metadata
    file does not exist.
    """
    try:
        with open('/etc/ravello/vm.json') as fin:
            return json.loads(fin.read())
    except IOError:
        return


@util.memoize
def get_ssh_environ():
    """Return the environment needed when running under SSH."""
    env = {}
    env['DEBUG'] = os.environ.get('DEBUG', '0')
    for key in ('RAVELLO_USERNAME', 'RAVELLO_PASSWORD', 'SSH_ORIGINAL_COMMAND'):
        if key not in os.environ:
            raise RuntimeError('missing environment variable: ${}'.format(key))
        env[key] = os.environ[key]
    app = os.environ.get('RAVELLO_APPLICATION')
    if app is None:
        meta = get_ravello_metadata()
        if meta is None:
            raise RuntimeError('missing environment variable: $RAVELLO_APPLICATION')
        app = meta['appName']
    env['RAVELLO_APPLICATION'] = app
    return env


@util.memoize
def get_ravello_client(env):
    """Return a connected Ravello client."""
    client = RavelloClient(env['RAVELLO_USERNAME'], env['RAVELLO_PASSWORD'])
    client.login()
    return client


_virsh_commands = [
    ('start', re.compile('virsh start ([^ ]+)')),
    ('stop', re.compile('virsh destroy ([^ ]+)')),
    ('reboot', re.compile('virsh reset ([^ ]+)')),
    ('list_all', re.compile('list --all.*tail')),
    ('list_running', re.compile('list --all.*running')),
    ('get_node_macs', re.compile('virsh dumpxml ([^ ]+) .*mac'))
]


def parse_virsh_command_line(env):
    """Parse the virsh command line.

    The proxy script is run as a forced command specified in an ssh private
    key. The original command is available in the $SSH_ORIGINAL_COMMAND
    environment variable.
    """
    command = env['SSH_ORIGINAL_COMMAND']
    for cmd, regex in _virsh_commands:
        match = regex.search(command)
        if match:
            return (cmd,) + match.groups()
    raise RuntimeError('unrecognized command: {}'.format(command))


def get_app_fail(env, client):
    """Return the application in $RAVELLO_APPLICATION.

    An exception is raised if the application does not exist.
    """
    name = env['RAVELLO_APPLICATION']
    apps = client.get_applications(filter={'name': name})
    if not apps:
        raise RuntimeError('application {} does not exist'.format(name))
    return client.get_application(apps[0]['id'])


def get_app_vm_fail(env, client, nodename):
    """Return the application and VM from $RAVELLO_APPLICATION and *nodename*.

    An exception is raised if the application or the VM does not exist.
    """
    app = get_app_fail(env, client)
    for vm in app.get('deployment', {}).get('vms', []):
        if vm['name'] == nodename:
            return app, vm
    raise RuntimeError('VM {} not found in application {}'.format(nodename, app['name']))


def do_start(env, client, nodename):
    """Start the VM with name *nodename*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    client.start_vm(app, vm)


def do_stop(env, client, nodename):
    """Stop the VM with name *nodename*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    client.stop_vm(app, vm)


def do_reboot(env, client, nodename):
    """Reboot the VM with name *nodename*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    client.restart_vm(app, vm)


def do_list_all(env, client):
    """List all VMs, output to standard out."""
    app = get_app_fail(env, client)
    for vm in app.get('deployment', {}).get('vms', []):
        sys.stdout.write('{}\n'.format(vm['name']))


def do_list_running(env, client):
    """List all running VMs, output to standard out."""
    app = get_app_fail(env, client)
    for vm in app.get('deployment', {}).get('vms', []):
        # Due to an idiosyncracy in the ssh power driver in Ironic, this needs
        # to be a quoted list of VMs (unlike for list_all).
        if vm['state'] in ('STARTING', 'STARTED'):
            sys.stdout.write('"{}"\n'.format(vm['name']))


def do_get_node_macs(env, client, nodename):
    """Return the Macs for all VMs, output to standard out."""
    app, vm = get_app_vm_fail(env, client, nodename)
    for conn in vm.get('networkConnections', []):
        mac = conn.get('device', {}).get('mac')
        if mac:
            sys.stdout.write('{}\n'.format(mac.replace(':', '')))


def _main():
    """The real main function."""
    log = util.get_logger()
    log.debug('New request, command = {}'.format(os.environ['SSH_ORIGINAL_COMMAND']))

    env = get_ssh_environ()
    client = get_ravello_client(env)
    cmdline = parse_virsh_command_line(env)

    log.debug('Parsed command = {!r}'.format(cmdline))

    if cmdline[0] == 'start':
        do_start(env, client, cmdline[1])
    elif cmdline[0] == 'stop':
        do_stop(env, client, cmdline[1])
    elif cmdline[0] == 'reboot':
        do_reboot(env, client, cmdline[1])
    elif cmdline[0] == 'list_all':
        do_list_all(env, client, )
    elif cmdline[0] == 'list_running':
        do_list_running(env, client, )
    elif cmdline[0] == 'get_node_macs':
        do_get_node_macs(env, client, cmdline[1])
    else:
        raise AssertionError('unknown command: {}'.format(cmdline[0]))


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
