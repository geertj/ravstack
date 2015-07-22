#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

import textwrap
from urllib.parse import urlparse

from . import ravello, util


def build_mac_map(servers):
    """Build a Mac -> (IP, name, aliases) map for a list of Nova servers."""
    mac_map = {}
    for server in servers:
        name = server.name[10:] if server.name.startswith('overcloud-') else server.name
        aliases = (server.name, getattr(server, 'OS-EXT-SRV-ATTR:instance_name'))
        for addr in server.addresses['ctlplane']:
            mac = addr['OS-EXT-IPS-MAC:mac_addr']
            mac_map[mac] = (addr['addr'], name, aliases)
    return mac_map


def update_networking(vm, mac_map):
    """Update """
    for conn in vm.get('networkConnections', []):
        mac = ravello.get_mac(conn)
        if mac in mac_map:
            break
    else:
        return False
    ip, name, aliases = mac_map[mac]
    updated = False
    aucfg = conn['ipConfig'].get('autoIpConfig')
    stcfg = conn['ipConfig'].get('staticIpConfig')
    if stcfg and stcfg.get('ip') != ip:
        stcfg['ip'] = ip
        updated = True
    elif aucfg and aucfg.get('reservedIp') != ip:
        aucfg['reservedIp'] = ip
        updated = True
    if vm['name'] != name:
        vm['name'] = name
        updated = True
    if sorted(vm.get('hostnames', [])) != sorted(aliases):
        vm['hostnames'] = aliases
        updated = True
    return updated


_control_services = [
    {'name': 'http', 'portRange': '80', 'protocol': 'TCP', 'external': True},
    {'name': 'vnc', 'portRange': '6080', 'protocol': 'TCP', 'external': True}, ]

def update_services(vm, mac_map):
    """Update services for VMs."""
    updated = False
    services = vm.setdefault('suppliedServices', [])
    for req in _control_services:
        req = req.copy()
        for ip, name, aliases in mac_map.values():
            if name == vm['name']:
                break
        else:
            continue
        req['ip'] = ip
        service = ravello.get_service(vm, req['portRange'])
        if not service:
            services.append(req)
        elif util.filter_dict(service, *req.keys()) != req:
            service.clear()  # nuke "id" otherwise update is not applied
            service.update(req)
        else:
            continue
        updated = True
    return updated


def do_network(env):
    """The `fixup-network` command.

    This updates the VM name, name aliases, and IP addresses on the Ravello
    VMs, and adds external services to the controller nodes
    """
    app = env.application
    ctrlname = env.config['tripleo']['controller_name']
    # Theory of operation: we list all instances on the undercloud, which are
    # also VMs in Ravello. We use the Mac address as a unique identifier to
    # know which one is which. For each VM in Ravello, update the IP address,
    # the host name, add some aliases. Then for controller nodes only, enable
    # some external services.
    updated = set()
    nova = env.nova_under
    nodes = nova.servers.list()
    mac_map = build_mac_map(nodes)
    # IPs / name / aliases
    for vm in ravello.get_vms(app, 'design'):
        if update_networking(vm, mac_map):
            updated.add(vm['name'])
    # Add required services
    for vm in ravello.get_vms(app, 'design'):
        if ctrlname not in vm['name']:
            continue
        if update_services(vm, mac_map):
            updated.add(vm['name'])
    if not updated:
        return
    env.client.call('PUT', '/applications/{id}'.format(**app), app)
    env.client.call('POST', '/applications/{id}/publishUpdates'.format(**app))
    print('Updated node{}: {}.'.format('s' if updated else '',
                                       ', '.join(sorted(updated))))


def add_httpd_server_alias(env, addr, nodename):
    """Add a ServerAlias for *.srv.ravcloud.com on a control node."""
    log = env.logger
    user = env.config['tripleo']['ssh_user']
    addr = '{}@{}'.format(user, addr)
    ctrlname = env.config['tripleo']['controller_name']
    log.debug('Inspecting httpd config on node `{}`.'.format(nodename))
    # Find the file for the ServerAlias setting.
    command = 'sudo grep -lE "ServerName.*{}" /etc/httpd/conf.d/*'.format(ctrlname)
    output = util.run_ssh(addr, command)
    fname = output.rstrip()
    log.debug('Remote config file is `{}`.'.format(fname))
    # See if the ServerAlias is already there..
    command = 'sudo grep -lE "ServerAlias.*srv.ravcloud.com" {} || true'.format(fname)
    output = util.run_ssh(addr, command)
    if output:
        log.debug('Node is up to date.')
        return False
    # If not, then add it using an ed script.
    command = 'sudo ed {}'.format(fname)
    script = textwrap.dedent("""\
            /ServerName
            a
              ServerAlias *.srv.ravcloud.com
            .
            ,w
            Q
            """)
    util.run_ssh(addr, command, input=script)
    log.debug('Updated httpd config on node `{}`.'.format(nodename))
    command = 'sudo systemctl restart httpd'
    util.run_ssh(addr, command)
    log.debug('Restarted httpd on node `{}`.'.format(nodename))
    return True


def update_nova_vnc_url(env, addr, nodename, newaddr):
    """Fix the nova vnc url on a compute node."""
    log = env.logger
    user = env.config['tripleo']['ssh_user']
    addr = '{}@{}'.format(user, addr)
    log.debug('Inspecting nova.conf on node `{}`.'.format(nodename))
    command = 'sudo crudini --get /etc/nova/nova.conf DEFAULT novncproxy_base_url'
    output = util.run_ssh(addr, command)
    current = output.rstrip()
    log.debug('Current vnc url = `{}`.'.format(current))
    parsed = urlparse(current)
    if parsed.netloc == newaddr:
        log.debug('Node is up to date.')
        return False
    newurl = current.replace(parsed.netloc, newaddr)
    log.debug('Updating vnc url to `{}`.'.format(newurl))
    command = 'sudo crudini --set /etc/nova/nova.conf DEFAULT' \
                    ' novncproxy_base_url "{}"'.format(newurl)
    util.run_ssh(addr, command)
    log.debug('Updated nova.conf on node `{}`.'.format(nodename))
    command = 'sudo systemctl restart openstack-nova-compute'
    util.run_ssh(addr, command)
    log.debug('Restarted nova-compute on node `{}`.'.format(nodename))
    return True


def do_nodes(env):
    """The `fixup-nodes` command.

    This command changes the ServerAlias on the horizon node so that it will
    accept the public Ravello DNS name. It will also set the VNC proxy URL on
    the compute nodes to point to the external IP of horizon.
    """
    app = env.application
    ctrlname = env.config['tripleo']['controller_name']
    compname = env.config['tripleo']['compute_name']
    # First update all the controllers with a ServerAlias.
    # Also try to find the external IP and port for the novnc service on port
    # 6080. This public IP/port will be set as the VNC URL on the compute
    # nodes. Note that in this configuration, VNC access goes directly to one
    # of controller, not to the VIP that is managed by the HAProxy. This is
    # identical to horizon itslef, which is also accesssed without HAProxy.
    vncaddr = None
    updated = set()
    for vm in ravello.get_vms(app, 'deployment'):
        if ctrlname not in vm['name']:
            continue
        service = ravello.get_service(vm, '80')
        if service and add_httpd_server_alias(env, service['ip'], vm['name']):
            updated.add(vm['name'])
        service = ravello.get_service(vm, '6080')
        if not service:
            continue
        conn = ravello.get_network(vm, service['ip'])
        if conn is None:
            continue
        extip = conn['ipConfig'].get('publicIp')
        if extip is None:
            continue
        extport = service.get('externalPort', service['portRange'])
        vncaddr = '{}:{}'.format(extip, extport)
    # Now update the VNC URLs.
    for vm in ravello.get_vms(app, 'deployment'):
        if compname not in vm['name']:
            continue
        if update_nova_vnc_url(env, service['ip'], vm['name'], vncaddr):
            updated.add(vm['name'])
    if updated:
        print('Updated node{}: {}.'.format('s' if updated else '',
                                           ', '.join(sorted(updated))))
