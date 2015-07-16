#
# This file is part of raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the raviron authors. See the file "AUTHORS" for a
# complete list.

import re
import os
import sys
import time
import shlex
import random
import subprocess
import textwrap

from . import util, ravello, logging


# proxy-create command

def create_ssh_keypair(keyname, comment):
    """Create a new ssh keypair."""
    sshdir = os.path.join(util.get_homedir(), '.ssh')
    util.create_directory(sshdir, 0o700)
    keyfile = os.path.join(sshdir, keyname)
    if util.try_stat(keyfile):
        raise RuntimeError('~/.ssh/{} already exists'.format(keyname))
    subprocess.check_call(['ssh-keygen', '-f', keyfile, '-N', "", '-q', '-C', comment])
    os.chmod(keyfile, 0o600)
    os.chmod(keyfile + '.pub', 0o644)
    return keyfile


def create_proxy(proxyname):
    """Create a proxy wrapper."""
    # Running in a software collection?
    enable_scls = []
    scls = os.environ.get('X_SCLS', '')
    for scl in scls.split():
        with open('/etc/scl/conf/{}'.format(scl)) as fin:
            prefix = fin.readline().rstrip()
        enable_scls.append('. {}/{}/enable'.format(prefix, scl))
    if scls:
        enable_scls.append('X_SCLS={}'.format(shlex.quote(scls)))
        enable_scls.append('export X_SCLS')
    else:
        enable_scls.append('# No software collections enabled.')
    enable_scls = '\n'.join(enable_scls)
    # Running in a virtualenv?
    venv = os.environ.get('VIRTUAL_ENV')
    enable_venv = '. {}/bin/activate'.format(venv) if venv else '# No virtualenv enabled.'
    # Create the ~/bin directory if needed
    bindir = os.path.join(util.get_homedir(), 'bin')
    proxyfile = os.path.join(bindir, proxyname)
    util.create_directory(bindir, 0o755)
    contents = textwrap.dedent("""\
            #!/bin/sh
            {}
            {}
            exec raviron proxy-run
            """).format(enable_scls, enable_venv)
    with open(proxyfile, 'w') as fout:
        fout.write(contents)
    os.chmod(proxyfile, 0o700)
    return proxyfile


def install_proxy(pubkey, command):
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
    os.chmod(authfile, 0o600)


_key_name = 'id_raviron'
_proxy_name = 'raviron-proxy'

def create_main(env):
    """The `raviron proxy-create` command."""
    keyname = env.config['proxy']['key_name']
    proxyname = env.config['proxy']['proxy_name']
    keyfile = create_ssh_keypair(keyname, proxyname)
    proxyfile = create_proxy(proxyname)
    install_proxy(keyfile + '.pub', proxyfile)
    print('Private key created as: ~/.ssh/{}'.format(keyname))
    print('Proxy created at: ~/bin/{}'.format(proxyname))


# proxy-run command

# These are the virsh commands used by the ssh power driver in Ironic.
# They need to match and be kept up to date with the following file:
# https://github.com/openstack/ironic/blob/master/ironic/drivers/modules/ssh.py#L151

_virsh_commands = [
    ('start', re.compile(' start ([^ ]+)')),
    ('stop', re.compile(' destroy ([^ ]+)')),
    ('reboot', re.compile(' reset ([^ ]+)')),
    ('get_node_macs', re.compile(' dumpxml ([^ ]+) .*mac')),
    ('list_running', re.compile(' list --all.*running')),
    ('list_all', re.compile(' list --all')),
    ('get_boot_device', re.compile(' dumpxml ([^ ]+) .*boot')),
    ('set_boot_device', re.compile(r'boot dev=\\"([^\\]+)\\".* edit ([^ ]+)')),
]


def parse_virsh_command_line():
    """Parse the virsh command line.

    The proxy script is run as a forced command specified in an ssh private
    key. The original command is available in the $SSH_ORIGINAL_COMMAND
    environment variable.
    """
    command = os.environ.get('SSH_ORIGINAL_COMMAND')
    if command is None:
        raise RuntimeError('This command needs to be run through ssh.')
    for cmd, regex in _virsh_commands:
        match = regex.search(command)
        if match:
            return (cmd,) + match.groups()
    raise RuntimeError('unrecognized command: {}'.format(command))


def get_app_fail(env, client):
    """Return the application in $RAVELLO_APPLICATION."""
    name = env['RAVELLO_APPLICATION']
    apps = client.call('POST', '/applications/filter', ravello.simple_filter(name=name))
    if not apps:
        raise RuntimeError('application {} not found'.format(name))
    return client.call('GET', '/applications/{id}'.format(**apps[0]))


def get_vm(app, nodename, scope='deployment'):
    """Return the VM *nodename* from *app*."""
    for vm in app.get(scope, {}).get('vms', []):
        if vm['name'] == nodename:
            return vm
    raise RuntimeError('application {} unknown vm {}'.format(app['name'], nodename))


class Retry(RuntimeError):
    """Exception used to indicate to retry_operation() that it needs to
    retry."""


_default_retries = {409: 10}

def retry_operation(func, timeout=60, retries=None):
    """Retry an operation on various 4xx errors."""
    log = logging.get_logger()
    end_time = time.time() + timeout
    tries = {}
    if retries is None:
        retries = _default_retries
    count = 0
    delay = min(10, max(2, timeout/100))
    start_time = time.time()
    while end_time > time.time():
        count += 1
        try:
            func()
        except ravello.HTTPError as e:
            status = e.response.status_code
            if status not in retries:
                raise
            log.debug('Retry: {!s}'.format(e))
            tries.setdefault(status, 0)
            tries[status] += 1
            if not 0 < tries[status] < retries[status]:
                log.error('Max retries reached for status {} ({})'
                                .format(status, retries[status]))
                raise
            log.warning('Retry number {} out of {} for status {}.'
                            .format(tries[status], retries[status], status))
        except Retry as e:
            log.warning('Retry requested: {}.'.format(e))
        else:
            time_spent = time.time() - start_time
            log.debug('Operation succeeded after {} attempt{} ({:.2f} seconds).'
                            .format(count, 's' if count > 1 else '', time_spent))
            return
        loop_delay = delay + random.random()
        log.debug('Sleeping for {:.2f} seconds.'.format(loop_delay))
        time.sleep(loop_delay)
    time_spent = time.time() - start_time
    raise RuntimeError('Timeout retrying function `{.__name__}` ({:.2f} seconds).'
                        .format(func, time_spent))


def do_start(env, nodename):
    """Start the VM with name *nodename*."""
    log = env.logger
    app = env.application
    # First extend runtime to min_runtime, if needed.
    def extend_runtime():
        exp = {'expirationFromNowSeconds': min_runtime*60}
        env.client.call('POST', '/applications/{id}/setExpiration'.format(**app), exp)
    nextstop = app.get('nextStopTime')
    min_runtime = env.config['ravello'].getint('min_runtime')
    if nextstop and nextstop/1000 < (time.time() + min_runtime*60):
        # This call should not fail even if vms are in a transient state.
        log.debug('Expiration less than minimum requested, extending runtime.')
        retry_operation(extend_runtime)
    # Now start it up, taking into account the current vm state.
    is_retry = False
    def start_vm():
        nonlocal app, is_retry
        # Reload because someone else could have changed the power state in the
        # mean time.
        if is_retry:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
            vm = get_vm(app, nodename)
        is_retry = True
        vm = get_vm(app, nodename)
        state = vm['state']
        if state in ('STARTED', 'STARTING', 'RESTARTING'):
            return
        if state == 'STOPPING':
            raise Retry('Application in state `{}`'.format(state))
        # STOPPED
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/start'
                                    .format(app=env.application, vm=vm))
    # According to the docs, 400 means the application is in the middle of
    # another action, but I get 409 instead.
    # Retry just 3 times in case of HTTP errors. Most of the times the code
    # aborts early based on the state of the VM and doesn't actually try to
    # call the start action if we know it will fail. The retries here are for
    # race conditions where someone else started up the VM concurrently. In the
    # next iteration, we should detect the updated state and exit cleanly.
    log.debug('Starting vm `{}`.'.format(nodename))
    retry_operation(start_vm, 1200, {400: 3, 403: 3, 409: 3})
    env.application = app


def do_stop(env, nodename):
    """Stop the VM with name *nodename*."""
    log = env.logger
    app = env.application
    is_retry = False
    def stop_vm():
        nonlocal app, is_retry
        if is_retry:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
        is_retry = True
        vm = get_vm(app, nodename)
        state = vm['state']
        if state in ('STOPPED', 'STOPPING'):
            return
        if state in ('STARTING', 'RESTARTING'):
            raise Retry('Application in state `{}`'.format(state))
        # STARTED
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/poweroff'
                                    .format(app=env.application, vm=vm))
    log.debug('Stopping vm `{}`.'.format(nodename))
    retry_operation(stop_vm, 1200, {400: 3, 403: 3, 409: 3})
    env.application = app


def do_reboot(env, nodename):
    """Reboot the VM with name *nodename*."""
    log = env.logger
    app = env.application
    is_retry = False
    def stop_vm():
        nonlocal app, is_retry
        if is_retry:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
        is_retry = True
        vm = get_vm(app, nodename)
        state = vm['state']
        if state in ('STARTING', 'RESTARTING'):
            return
        if state == 'STOPPING':
            raise Retry('Application in state `{}`'.format(state))
        # STOPPED or STARTED
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/restart'
                                    .format(app=env.application, vm=vm))
    log.debug('Rebooting vm `{}`.'.format(nodename))
    retry_operation(stop_vm, 1200, {400: 3, 403: 3, 409: 3})
    env.application = app


def do_list_all(env):
    """List all VMs, output to standard out."""
    for vm in ravello.get_vms(env.application):
        sys.stdout.write('{}\n'.format(vm['name']))


def do_list_running(env):
    """List all running VMs, output to standard out."""
    for vm in ravello.get_vms(env.application):
        # Due to an idiosyncracy in the ssh power driver in Ironic, this needs
        # to be a quoted list of VMs (unlike for list_all).
        if vm['state'] in ('STARTING', 'STARTED'):
            sys.stdout.write('"{}"\n'.format(vm['name']))


def do_get_node_macs(env, nodename):
    """Return the macs for *nodename*, output to standard out."""
    vm = get_vm(env.application, nodename)
    for conn in vm.get('networkConnections', []):
        device = conn.get('device', {})
        mac = device.get('mac')
        if mac is None:
            mac = device.get('generatedMac')
        if mac:
            sys.stdout.write('{}\n'.format(mac.replace(':', '')))


def get_disk(vm):
    """Return the hard drive for *vm*."""
    for drive in vm.get('hardDrives', []):
        if drive['type'] == 'DISK':
            return drive
    raise RuntimeError('VM {} does not have a DISK'.format(vm['name']))


def do_get_boot_device(env, nodename):
    """Return the boot dervice for *nodename*."""
    vm = get_vm(env.application, nodename)
    drive = get_disk(vm)
    print('hd' if drive.get('boot') else 'network')


def do_set_boot_device(env, nodename, device):
    """Set the boot device for *nodename* to *device*."""
    log = env.logger
    app = env.application
    is_retry = False
    def set_boot_device():
        nonlocal app, is_retry
        if is_retry:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
        is_retry = True
        vm = get_vm(app, nodename)
        state = vm['state']
        if state in ('STARTING', 'STOPPING', 'RESTARTING'):
            raise Retry('Application in state `{}`'.format(state))
        vm = get_vm(app, nodename, 'design')
        drive = get_disk(vm)
        drive['boot'] = bool(device == 'hd')
        env.client.call('PUT', '/applications/{id}'.format(**app), app)
    log.debug('Setting boot device for node `{}` to `{}`'.format(nodename, device))
    retry_operation(set_boot_device, 1200, {400: 3, 403: 3, 409: 3})
    def publish_updates():
        env.client.call('POST', '/applications/{id}/publishUpdates'.format(**app))
    log.debug('Publishing updates for application `{name}`.'.format(**app))
    retry_operation(publish_updates)
    env.application = app


def run_main(env):
    """The `raviron proxy-run` command."""
    log = env.logger
    log.debug('New request, command = {}'.format(os.environ.get('SSH_ORIGINAL_COMMAND', '?')))

    cmdline = parse_virsh_command_line()
    log.info('Parsed command: {}'.format(' '.join(cmdline)))

    if cmdline[0] == 'start':
        do_start(env, cmdline[1])
    elif cmdline[0] == 'stop':
        do_stop(env, cmdline[1])
    elif cmdline[0] == 'reboot':
        do_reboot(env, cmdline[1])
    elif cmdline[0] == 'list_all':
        do_list_all(env)
    elif cmdline[0] == 'list_running':
        do_list_running(env)
    elif cmdline[0] == 'get_node_macs':
        do_get_node_macs(env, cmdline[1])
    elif cmdline[0] == 'get_boot_device':
        do_get_boot_device(env, cmdline[1])
    elif cmdline[0] == 'set_boot_device':
        do_set_boot_device(env, cmdline[2], cmdline[1])
