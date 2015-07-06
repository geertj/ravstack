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
import time

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


# These are the virsh commands used by the ssh power driver in Ironic.
# They need to match and be kept up to date with the following file:
# https://github.com/openstack/ironic/blob/master/ironic/drivers/modules/ssh.py#L151

_virsh_commands = [
    ('start', re.compile('start ([^ ]+)')),
    ('stop', re.compile('destroy ([^ ]+)')),
    ('reboot', re.compile('reset ([^ ]+)')),
    ('get_node_macs', re.compile('dumpxml ([^ ]+) .*mac')),
    ('list_running', re.compile('list --all.*running')),
    ('list_all', re.compile('list --all')),
    ('get_boot_device', re.compile('dumpxml ([^ ]+) .*boot')),
    ('set_boot_device', re.compile(r'boot dev=\\"([^\\]+)\\".* edit ([^ ]+)')),
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


def _get_vm(app, nodename):
    """Return the VM *nodename* from *app*."""
    for vm in app.get('deployment', {}).get('vms', []):
        if vm['name'] == nodename:
            return vm
    raise RuntimeError('App {} does not have a VM {}'.format(app['name'], nodename))


def get_app_vm_fail(env, client, nodename):
    """Return the application and VM from $RAVELLO_APPLICATION and *nodename*.

    An exception is raised if the application or the VM does not exist.
    """
    app = get_app_fail(env, client)
    vm = _get_vm(app, nodename)
    return app, vm


def _wait_for_status(env, client, nodename, state, timeout=600):
    """Wait until *nodename* is in *state*."""
    inverse = state.startswith('!')
    wait_state = state.lstrip('!')
    log = util.get_logger()
    end_time = time.time() + timeout
    while end_time > time.time():
        log.debug('_wait_for_status(): waiting for {}'.format(state))
        app, vm = get_app_vm_fail(env, client, nodename)
        log.debug('_wait_for_status(): state = {}'.format(vm['state']))
        if not inverse and vm['state'] == wait_state or \
                inverse and vm['state'] != wait_state:
            break
        time.sleep(10)
    raise RuntimeError('VM {} timeout waiting for {}'.format(nodename, state))


def do_start(env, client, nodename):
    """Start the VM with name *nodename*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    state = vm['state']
    if state in ('STARTED', 'STARTING'):
        return
    if state == 'STOPPING':
        # Need to wait until it is in STOPPED, otherwise it cannot be started.
        _wait_for_status(env, client, nodename, 'STOPPED')
    client.start_vm(app, vm)
    # Wait for STARTING, and then !STARTING. This is more reliable than waiting
    # for STARTED, as someone else could have stopped in the mean time.
    _wait_for_status(env, client, nodename, 'STARTING')
    _wait_for_status(env, client, nodename, '!STARTING')


def do_stop(env, client, nodename):
    """Stop the VM with name *nodename*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    state = vm['state']
    if state in ('STOPPED', 'STOPPING'):
        return
    if state == 'STARTING':
        _wait_for_status(env, client, nodename, 'STARTED')
    client.stop_vm(app, vm)
    _wait_for_status(env, client, nodename, 'STOPPING')
    _wait_for_status(env, client, nodename, '!STOPPING')


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
    """Return the macs for *nodename*, output to standard out."""
    app, vm = get_app_vm_fail(env, client, nodename)
    for conn in vm.get('networkConnections', []):
        device = conn.get('device', {})
        mac = device.get('mac')
        if mac is None:
            mac = device.get('generatedMac')
        sys.stdout.write('{}\n'.format(mac.replace(':', '')))


def _get_disk(vm):
    """Return the hard drive for *vm*."""
    for drive in vm.get('hardDrives', []):
        if drive['type'] == 'DISK':
            return drive
    raise RuntimeError('VM {} does not have a DISK'.format(vm['name']))


def do_get_boot_device(env, client, nodename):
    """Return the boot dervice for *nodename*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    drive = _get_disk(vm)
    return 'hd' if drive.get('boot') else 'network'


def _retry_on_conflict(env, client, func, timeout=600, delay=10):
    """Retry a function in case it raises a 409 Conflict."""
    log = util.get_logger()
    end_time = time.time() + timeout
    while end_time > time.time():
        try:
            func()
        except Exception as e:
            if not hasattr(e, 'response') or e.response.status_code != 409:
                raise
            log.debug('_retry_on_conflict(): retrying conflict')
        time.sleep(delay)


def do_set_boot_device(env, client, nodename, device):
    """Set the boot device for *nodename* to *device*."""
    app, vm = get_app_vm_fail(env, client, nodename)
    appid = app['id']
    # We need to reload and retry saving back the application as there's
    # nothing preventing concurrent modifications. Fortunately Ravello detects
    # this using a "version" key that is part of the app. This also explains wy
    # we reload the app on every iteration below.
    def set_boot_device():
        app = client.get_application(appid)
        vm = _get_vm(app, nodename)
        drive = _get_disk(vm)
        drive['boot'] = bool(device == 'hd')
        client.update_application(app)
    _retry_on_conflict(env, set_boot_device, 60, 1)
    # Same for publish changes. Here we wait longer because we cannot publish
    # updates if there's a VM in a transient state (STARTING / STOPPING).
    def publish_updates():
        client.publish_application_updates(appid)
    _retry_on_conflict(env, publish_updates, 600, 10)


def _main():
    """The real main function."""
    log = util.get_logger()
    log.debug('New request, command = {}'.format(os.environ['SSH_ORIGINAL_COMMAND']))

    env = get_ssh_environ()

    cmdline = parse_virsh_command_line(env)
    log.debug('Parsed command = {!r}'.format(cmdline))

    client = get_ravello_client(env)

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
    elif cmdline[0] == 'get_boot_device':
        do_get_boot_device(env, client, cmdline[1])
    elif cmdline[0] == 'set_boot_device':
        do_set_boot_device(env, client, cmdline[2], cmdline[1])
    else:
        raise AssertionError('unknown command: {}'.format(cmdline[0]))


def main():
    """Main wrapper function.

    Calls _main() and handles any exceptions that might occur.
    """
    try:
        _main()
    except Exception as e:
        log = util.get_logger()
        log.error('Uncaught exception:', exc_info=True)
        if util.get_debug():
            raise
        sys.stdout.write('Error: {!s}\n'.format(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
