#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
import sys
import json
import time
import tempfile
import re

from . import util, ravello
from .util import inet_aton, inet_ntoa
from .ravello import retry_operation


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
            'description': 'Node created by ravstack.',
            'os': 'linux_manuel',  # sic
            'baseVmId': 0,
            'numCpus': env.args['--cpus'],
            'memorySize': {'value': env.args['--memory'], 'unit': 'MB'},
            'stopTimeOut': 180,
            'cpuIds': ravello.magic_svm_cpuids}

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

    # Network services: enable ssh on the same network interface as the controller.
    service = ravello.get_service(env.nodes[0], '22')
    for ssh_idx, conn in enumerate(env.nodes[0]['networkConnections']):
        if ravello.get_ip(conn) == service['ip']:
            break
    else:
        ssh_idx = None
    if ssh_idx is not None:
        mgmt_ip = conns[ssh_idx]['ipConfig']['staticIpConfig']['ip']
        services = node['suppliedServices'] = []
        services.append({'name': 'ssh',
                         'portRange': '22',
                         'protocol': 'TCP',
                         'external': True,
                         'ip': mgmt_ip})
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


def dump_nodes(env):
    """Dump the nodes to the nodes file."""
    # The nodes file (typically ~/instackenv.json) contains information about
    # the available nodes, their mac addresses and power management
    # credentials. It is read by "openstack baremetal import" when it creates
    # the nodes in Ironic.
    keyname = env.config['proxy']['key_name']
    keyfile = os.path.join(util.get_homedir(), '.ssh', keyname)
    if not util.can_open(keyfile):
        raise RuntimeError('`~/.ssh/{}` does not exist.'.format(keyname))
    with open(keyfile) as fin:
        privkey = fin.read()
    nodes = []
    for vm in env.nodes[1:]:
        node = {'name': vm['name'],
                'arch': 'x86_64',
                'cpu': str(vm['numCpus']),
                'memory': str(ravello.convert_size(vm['memorySize'], 'MB')),
                'disk': str(ravello.convert_size(vm['hardDrives'][0]['size'], 'GB'))}
        macs = node['mac'] = []
        for nic in vm['networkConnections']:
            mac = ravello.get_mac(nic)
            if mac:
                macs.append(mac)
        node.update({'pm_type': 'pxe_ssh',
                     'pm_addr': 'localhost',
                     'pm_user': util.get_user(),
                     'pm_password': privkey})
        nodes.append(node)
    nodes_file = env.config['tripleo']['nodes_file']
    fname = os.path.expanduser(nodes_file)
    with open(fname, 'w') as fout:
        fout.write(json.dumps({'nodes': nodes}, sort_keys=True, indent=2))
    print('Wrote {} nodes to `{}`.'.format(len(nodes), nodes_file))


_ethers_file = '/etc/ethers'

def dump_ethers(env):
    """Write the /etc/ethers file."""
    # The /etc/ethers file is used so that the dnsmasq for the access network
    # allocates the right address for our nodes. This removes the need for us
    # to fix things up later (like for the management network).
    if not util.can_run_sudo():
        print('Warning: no sudo access, not writing `{}`.'.format(_ethers_file))
        return
    ethers = []
    for node in env.nodes[1:]:
        for conn in node['networkConnections']:
            mac = ravello.get_mac(conn)
            ip = ravello.get_ip(conn)
            if mac and ip:
                ethers.append((mac, ip))
    fd, tmpname = tempfile.mkstemp()
    with open(fd, 'w') as fout:
        for mac, ip in ethers:
            fout.write('{} {}\n'.format(mac, ip))
    util.run_sudo(['chown', '0:0', tmpname])
    util.run_sudo(['chmod', '644', tmpname])
    if util.selinux_enabled():
        util.run_sudo(['chcon', '--reference', '/etc/hosts', tmpname])
    util.run_sudo(['mv', tmpname, _ethers_file])
    util.run_sudo(['systemctl', 'restart', 'dnsmasq'])
    print('Wrote {} mac addresses to `{}`.'.format(len(ethers), _ethers_file))


def do_dump(env):
    """The `node-dump` command."""
    dump_nodes(env)
    dump_ethers(env)


# Ravello has six VM states. Mapping to Ironic power states:
# STOPPING, STOPPED -> OFF
# STARTING, STARTED, UPDATING, RESTARTING -> ON

def do_list_running(env, virsh_format=False):
    """The `node-list command."""
    for node in env.nodes[1:]:
        name = node['name']
        if virsh_format:
            # Yes it needs quotes, unlike do_list_all().
            name = '"{}"'.format(name)
        if node['state'] not in ('STOPPING', 'STOPPED'):
            sys.stdout.write('{}\n'.format(name))


def do_list_all(env):
    """The `node-list --all` command."""
    nodes_file = env.config['tripleo']['nodes_file']
    fname = os.path.expanduser(nodes_file)
    # If we're called from the proxy try to use cached information from the
    # nodes file. We take this approach for `node-list --all` and also for
    # `get-node-macs` below. Ironic will refresh the power states for each node
    # every minute or so. To find the name of a node, it will list all nodes,
    # and then list the mac addresses for each node until it finds the node.
    # This is very inefficient. Together these two calls account for about 75%
    # of all API calls made by Ironic. It also causes problems because the node
    # is locked by Ironic during these API calls and this sometimes causes
    # exernal API clients to reach their maximum retry.
    # The information for both API calls does not change unless someone first
    # adds a node and then dumps the info to the nodes file, and then imports
    # it in Ironic. So rather than contacting the API, we get the information
    # from the nodes file directly, if it exists.
    if env.args['--cached'] and util.try_stat(fname):
        with open(fname) as fin:
            nodes = json.loads(fin.read())['nodes']
    else:
        # This is computed on attribute access. So we are actually preventing
        # the API calls if we don't access it.
        nodes = env.nodes[1:]
    for node in nodes:
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
    is_retry = [False]  # nonlocal
    def start_vm():
        # Reload because someone else could have changed the application.
        app = env.application
        if is_retry[0]:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
            env.application = app
        is_retry[0] = True
        vm = get_vm(app, nodename)
        log.debug('Node `{name}` is in state `{state}`.'.format(**vm))
        state = vm['state']
        # STARTED, or a transient state that will result in STARTED: done
        if state in ('STARTING', 'STARTED', 'RESTARTING', 'UPDATING'):
            return
        # STOPPING will result in STOPPED. Need to wait, cannot do anything right now.
        elif state == 'STOPPING':
            raise ravello.Retry('Node in state `{}`'.format(state))
        # Is there a scheduled change of boot device?
        bootdev = get_next_boot_device(vm)
        if bootdev:
            log.debug('Updating boot device to `{}`.'.format(bootdev))
            design_vm = get_vm(app, nodename, 'design')
            set_current_boot_device(design_vm, bootdev)
            clear_next_boot_device(design_vm)
            app = env.client.call('PUT', '/applications/{id}'.format(**app), app)
            env.client.call('POST', '/applications/{id}/publishUpdates'.format(**app))
            env.application = app
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/start'
                                    .format(app=app, vm=vm))
    # According to the docs, 400 means the application is in the middle of
    # another action, but I get 409 instead.
    # Retry just 3 times in case of HTTP errors. The start_vm function will not
    # try to start the VM if that would not be possible (e.g. the VM is in
    # STOPPING). The retries here are for race conditions where someone else
    # started up the VM concurrently.
    log.debug('Starting node `{}`.'.format(nodename))
    retry_operation(start_vm, 1200, {400: 3, 403: 3, 409: 3})


def do_stop(env, nodename):
    """The `node-stop` command."""
    log = env.logger
    is_retry = [False]  # nonlocal
    def stop_vm():
        app = env.application
        if is_retry[0]:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
            env.application = app
        is_retry[0] = True
        vm = get_vm(app, nodename)
        log.debug('Node `{name}` is in state `{state}`.'.format(**vm))
        state = vm['state']
        # STOPPED, or STOPPING which will result in STOPPED: done
        if state in ('STOPPED', 'STOPPING'):
            return
        # These states will result in STARTED but prevent us from doing
        # anything right now. So wait.
        elif state in ('STARTING', 'RESTARTING', 'UPDATING'):
            raise ravello.Retry('Node in state `{}`'.format(state))
        # STARTED
        env.client.call('POST', '/applications/{app[id]}/vms/{vm[id]}/poweroff'
                                    .format(app=env.application, vm=vm))
    log.debug('Stopping node `{}`.'.format(nodename))
    retry_operation(stop_vm, 1200, {400: 3, 403: 3, 409: 3})


def do_reboot(env, nodename):
    """The `node-reboot` command."""
    do_stop(env, nodename)
    del env.application  # re-init it with the correct VM state
    do_start(env, nodename)


# Boot device stuff. This is somewhat complicated. Changing the boot device on
# Ravello will restart a VM. Ironic does not expect that. So we use a hack
# whereby if a boot device change is requested while a VM is not in the STOPPED
# state, that we "queue" this change into the VM's description and execute it
# only at the next power change.

def get_current_boot_device(vm):
    """Return the current boot device for a VM."""
    drive = get_disk(vm)
    return 'hd' if drive.get('boot') else 'network'

def set_current_boot_device(vm, bootdev):
    """Set the current boot device for a VM."""
    drive = get_disk(vm)
    drive['boot'] = (bootdev == 'hd')


_re_bootdev = re.compile('\\[boot: (hd|network)\\]')

def get_next_boot_device(vm):
    """Return the next boot device for a VM, if any."""
    # Yes, we do indeed abuse the "description" field for this...
    desc = vm.get('description', '')
    match = _re_bootdev.search(desc)
    return match.group(1) if match else None

def set_next_boot_device(vm, bootdev):
    """Schedule a boot device change."""
    desc = vm.get('description', '')
    match = _re_bootdev.search(desc)
    current = match.group(1) if match else None
    if current == bootdev:
        return
    if current:
        desc = desc[:match.start(0)] + desc[match.end(0)+1:]
    desc += '[boot: {}]'.format(bootdev)
    vm['description'] = desc

def clear_next_boot_device(vm):
    """Clear any pending boot device change."""
    desc = vm.get('description', '')
    match = _re_bootdev.search(desc)
    if not match:
        return
    desc = desc[:match.start(0)] + desc[match.end(0)+1:]
    vm['description'] = desc


def get_boot_device(vm):
    """Get the effective boot device."""
    bootdev = get_next_boot_device(vm)
    if bootdev is None:
        bootdev = get_current_boot_device(vm)
    return bootdev


def do_get_boot_device(env, nodename):
    """The `node-get-boot-device` command."""
    vm = get_vm(env.application, nodename)
    bootdev = get_boot_device(vm)
    print(bootdev)


def do_set_boot_device(env, nodename, bootdev):
    """Set the boot device for *nodename* to *bootdev*."""
    log = env.logger
    is_retry = [False]  # nonlocal
    def set_boot_device():
        app = env.application
        if is_retry[0]:
            app = env.client.call('GET', '/applications/{id}'.format(**app))
            env.application = app
        is_retry[0] = True
        vm = get_vm(app, nodename)
        current = get_boot_device(vm)
        if current == bootdev:
            log.debug('Boot device already set to `{}`.'.format(bootdev))
            return
        state = vm['state']
        design_vm = get_vm(app, nodename, 'design')
        # Is it a matter of removing the next boot device?
        if get_current_boot_device(vm) == bootdev:
            clear_next_boot_device(design_vm)
            log.debug('Clearing next boot device.')
        # Nope: need to updated the real boot device.
        # We can do this when state == STOPPED.
        elif state == 'STOPPED':
            set_current_boot_device(design_vm, bootdev)
            clear_next_boot_device(design_vm)
            log.debug('Setting current boot device to `{}`.'.format(bootdev))
        # Need to queue the boot device change.
        else:
            set_next_boot_device(design_vm, bootdev)
            log.debug('Setting next boot device to `{}`.'.format(bootdev))
        app = env.client.call('PUT', '/applications/{id}'.format(**app), app)
        env.client.call('POST', '/applications/{id}/publishUpdates'.format(**app))
        env.application = app
    log.debug('Setting boot device for node `{}` to `{}`'.format(nodename, bootdev))
    retry_operation(set_boot_device, 1200, {400: 3, 403: 3, 409: 3})


def do_get_macs(env, nodename, virsh_format=False):
    """The `node-get-macs` command."""
    nodes_file = env.config['tripleo']['nodes_file']
    fname = os.path.expanduser(nodes_file)
    # See the note in do_list_all on why we're using cached information.
    macs = []
    if env.args['--cached'] and util.try_stat(fname):
        with open(fname) as fin:
            nodes = json.loads(fin.read())['nodes']
        for node in nodes:
            if node['name'] == nodename:
                macs += node['mac']
    else:
        vm = get_vm(env.application, nodename)
        for conn in vm.get('networkConnections', []):
            mac = ravello.get_mac(conn)
            if mac:
                macs.append(mac)
    for mac in macs:
        if virsh_format:
            mac = mac.replace(':', '')
        sys.stdout.write('{}\n'.format(mac))
