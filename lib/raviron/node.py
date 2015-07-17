#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

import os
import sys
import json
import time
import random

from . import util, ravello, logging
from .util import inet_aton, inet_ntoa


_magic_svm_cpuids = [
    {"index": "0", "value": "0000000768747541444d416369746e65"},
    {"index": "1", "value": "000006fb00000800c0802000078bfbfd"},
    {"index": "8000000a", "value": "00000001000000400000000000000089"},
    {"index": "80000000", "value": "8000000a000000000000000000000000"},
    {"index": "80000001", "value": "00000000000000000000001520100800"}, ]


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


def get_vm(app, nodename, scope='deployment'):
    """Return the VM *nodename* from *app*."""
    for vm in app.get(scope, {}).get('vms', []):
        if vm['name'] == nodename:
            return vm
    raise RuntimeError('Application `{}` unknown vm `{}`.'.format(app['name'], nodename))


def get_disk(vm):
    """Return the hard drive for *vm*."""
    for drive in vm.get('hardDrives', []):
        if drive['type'] == 'DISK':
            return drive
    raise RuntimeError('VM {} does not have a DISK'.format(vm['name']))


def find_all_ips(app, subnet, mask):
    """Yield all IPs in the application that are on subnet/mask."""
    subnet = inet_aton(subnet)
    for scope in ('deployment', 'design'):
        for vm in ravello.get_vms(app, scope):
            for conn in vm.get('networkConnections', []):
                scfg = conn.get('ipConfig', {}).get('staticIpConfig', {})
                if 'ip' not in scfg or 'mask' not in scfg:
                    continue
                if inet_aton(scfg['ip']) & inet_aton(scfg['mask']) == subnet \
                            and scfg['mask'] == mask:
                    yield scfg['ip']


def create_node(env, new_name):
    """Create a new node and return it."""
    node = {'name': new_name,
            'description': 'Node created by raviron.',
            'os': 'linux_manuel',  # sic
            'baseVmId': 0,
            'numCpus': env.args['--cpus'],
            'memorySize': {'value': env.args['--memory'], 'unit': 'MB'},
            'stopTimeOut': 180,
            'cpuIds': _magic_svm_cpuids}

    # disk drives
    drives = node['hardDrives'] = []
    drives.append({'index': 1,
                   'type': 'DISK',
                   'name': 'sda',
                   'boot': True,
                   'controller': 'virtio',
                   'size': {'value': env.args['--disk'], 'unit': 'GB'}})
    drives.append({'index': 2,
                   'type': 'CDROM',
                   'name': 'cdrom',
                   'controller': 'IDE',
                   'baseDiskImageId': env.iso['id']})

    # Networks is the most complicated part. The idea is to connect to every
    # subnet that is defined on the Ironic node, using an IP that is higher
    # than any other node on that subnet.

    # Add network interfaces by copying the ones from the Ironic node.

    delta = 1 if len(env.nodes) > 1 else 10
    conns = node['networkConnections'] = []

    for conn in env.nodes[0]['networkConnections']:
        dev = conn['device']
        icfg = conn['ipConfig']
        scfg = icfg['staticIpConfig']
        subnet = inet_ntoa(inet_aton(scfg['ip']) & inet_aton(scfg['mask']))
        max_ip = sorted(find_all_ips(env.application, subnet, scfg['mask']),
                        key=lambda ip: inet_aton(ip))[-1]
        new_ip = inet_ntoa(inet_aton(max_ip) + delta)
        if inet_ntoa(inet_aton(new_ip) & inet_aton(scfg['mask'])) != subnet:
            raise RuntimeError('no more IPs left for interface {name}'.format(**conn))
        scfg = scfg.copy()
        scfg['ip'] = new_ip
        conns.append({'name': conn['name'],
                      'device': {
                            'index': dev['index'],
                            'deviceType': dev['deviceType'],
                            'useAutomaticMac': True},
                      'ipConfig': {
                            'hasPublicIp': icfg['hasPublicIp'],
                            'externalAccessState': icfg['externalAccessState'],
                            'staticIpConfig': scfg}})

    # Network services: enable ssh on first network interface
    first_ip = conns[0]['ipConfig']['staticIpConfig']['ip']
    services = node['suppliedServices'] = []
    services.append({'name': 'ssh',
                     'portRange': '22',
                     'protocol': 'TCP',
                     'external': True,
                     'ip': first_ip})

    return node


def do_create(env):
    """The `node-create` command."""
    log = env.logger
    client = env.client

    app = env.application
    vms = ravello.get_vms(app)
    vm_names = [vm['name'] for vm in vms]

    try:
        count = int(env.args['--count'])
    except ValueError:
        raise ValueError('Illegal value for --count: {}'
                                .format(env.args['--count']))
    new_names = []

    # Create and add the nodes
    for i in range(count):
        name = util.unique_name_seqno('node{}', vm_names)
        vm_names.append(name)
        new_names.append(name)
        node = create_node(env, name)
        app['design']['vms'].append(node)
        env.nodes.append(node)

    # Extend runtime to minimum runtime if needed.
    nextstop = app.get('nextStopTime')
    min_runtime = env.config['ravello'].getint('min_runtime')
    if nextstop and nextstop/1000 < time.time() + min_runtime*60:
        log.debug('extending application runtime to {}s'.format(min_runtime))
        exp = {'expirationFromNowSeconds': min_runtime*60}
        client.call('POST', '/applications/{id}/setExpiration'.format(**app), exp)

    # Now update application and publish updates. Do not start new nodes.
    client.call('PUT', '/applications/{id}'.format(**app), app)
    client.request('POST', '/applications/{id}/publishUpdates'
                           '?startAllDraftVms=false'.format(**app))

    print('Created {} node{}: {}.'.format(count, 's' if count > 1 else '',
                                          ', '.join(new_names)))


def do_dump(env):
    """The `node-dump` command."""
    keyname = env.config['proxy']['key_name']
    keyfile = os.path.join(util.get_homedir(), '.ssh', keyname)
    if not util.can_open(keyfile):
        raise RuntimeError('`~/.ssh/{}` does not exist.\n'
                           'Use `raviron proxy-create` to create it.'
                           .format(keyname))
    with open(keyfile) as fin:
        privkey = fin.read()

    # Get node definitions from Ravello

    nodes = []
    for vm in env.nodes[1:]:
        node = {'arch': 'x86_64',
                'cpu': str(vm['numCpus']),
                'memory': str(ravello.convert_size(vm['memorySize'], 'MB')),
                'disk': str(ravello.convert_size(vm['hardDrives'][0]['size'], 'GB'))}
        macs = node['mac'] = []
        for nic in vm['networkConnections']:
            mac = nic['device'].get('mac')
            if mac is None:
                mac = nic['device']['generatedMac']
            macs.append(mac)
        node.update({'pm_type': 'pxe_ssh',
                     'pm_addr': 'localhost',
                     'pm_user': util.get_user(),
                     'pm_password': privkey})
        nodes.append(node)

    # Dump to ~/nodes.json

    nodes_file = env.config['nodes']['nodes_file']
    fname = os.path.expanduser(nodes_file)
    with open(fname, 'w') as fout:
        fout.write(json.dumps({'nodes': nodes}, sort_keys=True, indent=2))

    print('Wrote {} nodes to `{}`.'.format(len(nodes), nodes_file))


def do_list_running(env, virsh_format=False):
    """The `node-list command."""
    for node in env.nodes[1:]:
        name = node['name']
        if virsh_format:
            # Yes it needs quotes, unlike do_list_all().
            name = '"{}"'.format(name)
        if node['state'] in ('STARTING', 'STARTED'):
            sys.stdout.write('{}\n'.format(name))


def do_list_all(env):
    """The `node-list --all` command."""
    for node in env.nodes[1:]:
        sys.stdout.write('{}\n'.format(node['name']))


def do_start(env, nodename):
    """The `node-start` command."""
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
            raise Retry('Node in state `{}`'.format(state))
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
    """The `node-stop` command."""
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
            raise Retry('Node in state `{}`'.format(state))
        # STARTED
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/poweroff'
                                    .format(app=env.application, vm=vm))
    log.debug('Stopping vm `{}`.'.format(nodename))
    retry_operation(stop_vm, 1200, {400: 3, 403: 3, 409: 3})
    env.application = app


def do_reboot(env, nodename):
    """The `node-reboot` command."""
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
            raise Retry('Node in state `{}`'.format(state))
        # STOPPED or STARTED
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/restart'
                                    .format(app=env.application, vm=vm))
    log.debug('Rebooting vm `{}`.'.format(nodename))
    retry_operation(stop_vm, 1200, {400: 3, 403: 3, 409: 3})
    env.application = app


def do_get_boot_device(env, nodename):
    """The `node-get-boot-device` command."""
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
            raise Retry('Node in state `{}`'.format(state))
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


def do_get_macs(env, nodename, virsh_format=False):
    """The `node-get-macs` command."""
    vm = get_vm(env.application, nodename)
    for conn in vm.get('networkConnections', []):
        device = conn.get('device', {})
        mac = device.get('mac')
        if mac is None:
            mac = device.get('generatedMac')
        if not mac:
            continue
        if virsh_format:
            mac = mac.replace(':', '')
        if mac:
            sys.stdout.write('{}\n'.format(mac))
