#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

import os
import json
import time

from . import util, ravello
from .util import inet_aton, inet_ntoa


_magic_svm_cpuids = [
    {"index": "0", "value": "0000000768747541444d416369746e65"},
    {"index": "1", "value": "000006fb00000800c0802000078bfbfd"},
    {"index": "8000000a", "value": "00000001000000400000000000000088"},
    {"index": "80000000", "value": "8000000a000000000000000000000000"},
    {"index": "80000001", "value": "00000000000000000000001520100800"}, ]


# node-create command

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


def create_main(env):
    """The `raviron node-create` command."""
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


# node-sync command

def sync_main(env):
    """The `raviron node-sync` command."""
    app = env.application

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
