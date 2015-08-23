#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import sys
import time
import errno
import socket
import select
import struct
import httplib

from . import logging, args

LOG = logging.get_logger()

_default_base = 10000
_default_nports = 50
_default_timeout = 2


def get_public_ip():
    """Return the IP address that outgoing network connections appear to come
    from.

    This is also the IP address to use for inbound access. Note that in
    addition, an supplied service with the "external" flag set needs to be
    defined in Ravello.
    """
    # This uses ipify.org. See www.ipify.org. This is a free service running
    # open source code deployed on Heroku. ON the web site the author says he
    # intends to keep it around for years to come.
    conn = httplib.HTTPConnection('api.ipify.org', 80)
    try:
        conn.request('GET', '/')
        resp = conn.getresponse()
        if resp.status != httplib.OK:
            raise RuntimeError('api.ipify.org status {}'.format(resp.status))
        body = resp.read()
    finally:
        conn.close()
    return body


def inet_atoni(ip):
    """Like inet_aton() but returns an integer."""
    return struct.unpack('>I', socket.inet_aton(ip))[0]

def inet_nitoa(i):
    """Like inet_ntoa but expects an integer."""
    return socket.inet_ntoa(struct.pack('>I', i))


def find_in_connection_table(addr):
    """Find a peer address *addr* in the connection table, and return the
    socket address."""
    # Addresses in /proc/net/tcp are network endian printed as machine endian,
    # meaning they get byte swapped on little endian. Ports are machine endian
    # printed as machine endian i.e. never byte swapped.
    peer_addr = '{:08X}:{:04X}'.format(socket.ntohl(inet_atoni(addr[0])), addr[1])
    sock_addr = None
    with open('/proc/net/tcp') as fin:
        for line in fin:
            parts = line.split()
            if parts[2] == peer_addr:
                sp = parts[1].split(':')
                sock_addr = (inet_nitoa(socket.htonl(int(sp[0], 16))), int(sp[1], 16))
                break
    return sock_addr


def get_port_candidates(ports, base=None, nports=None):
    """Return a list of port mapping candidates."""
    if base is None:
        base = _default_base
    if nports is None:
        nports = _default_nports
    # Add both the ports themselves as well as the default portmapping range.
    # This makes the approach work when used with both public IPs and portmapping.
    return list(ports) + list(range(base, base+nports))


def find_external_endpoints(ports, candidates, timeout=None):
    """Find the external endpoints for a set of ports.

    The *services* argument must be a list of port numbers. The *timeout*
    parameter is the total time to spend for discovery.  The *low* and *high*
    paremeters specify the range to scan to find services that are portmapped.

    The return value is a dictionary mapping local port numbers to ``(ip,
    port)`` tuples.
    """
    # The approach: we know that Ravello maps ports starting at a fixed port.
    # We simply try a number of ports start at that port and try to connect to
    # it. If we can connect, see if the socket connects back to the service we
    # are interested in.
    #
    # A limitation of this approach is that it only supports ports that are
    # listening.
    #
    # Ravello, we really need an API for this that can be executed from within
    # a VM without having to store credentials!!

    if timeout is None:
        timeout = _default_timeout

    # First we do a non-blocking connect on all candidate ports in parallel.
    # Candidate ports are in the range from low to high, and also the ports
    # themselves (in case portmapping is not used).

    publicip = get_public_ip()
    LOG.debug('my public IP: `{}`.'.format(publicip))

    sockets = {}
    ports = list(ports)

    for cport in candidates:
        sock = socket.socket()
        sock.setblocking(False)
        try:
            sock.connect((publicip, cport))
        except socket.error as e:
            if e.args[0] != errno.EINPROGRESS:
                sock.close()
                continue
        sockets[sock.fileno()] = (sock, cport)

    LOG.debug('Initiated non-blocking connect for {} sockets'.format(len(sockets)))

    # Select loop where we wait for *timeout* seconds for the sockets to
    # connect. Once connect, we try to find the peer socket in /proc/net/tcp.
    # Note that we may not find it because the port may map to a different VM.

    endpoints = {}
    end_time = time.time() + timeout

    while True:
        timeout = end_time - time.time()
        if timeout < 0:
            break
        fds = [s.fileno() for s, _ in sockets.values()]
        try:
            _, wfds, _ = select.select([], fds, [], timeout)
        except select.error as e:
            if e.args[0] == errno.EINTR:
                continue
            raise
        for fd in wfds:
            sock, cport = sockets[fd]
            try:
                error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    LOG.debug('Socket to port {} errno {}'.format(cport, error))
                    raise socket.error(error)
                LOG.debug('Socket to port {} connected'.format(cport))
                paddr = (publicip, sock.getsockname()[1])
                saddr = find_in_connection_table(paddr)
                if saddr:
                    LOG.debug('Found in connection table: `{}:{}`.'.format(*saddr))
                if saddr and saddr[1] in ports:
                    endpoints[saddr[1]] = (publicip, cport)
                    ports.remove(saddr[1])
            except socket.error:
                pass
            sock.close()
            del sockets[fd]
        if not ports or not sockets:
            break

    # Clean up remaining sockets and return the result.
    for sock, _ in sockets.values():
        sock.close()
    sockets.clear()

    return endpoints


def do_resolve(env, port):
    """The `resolve-endpoint` command."""
    port = args.require_int(port, '<port>', minval=0, maxval=65535)
    timeout = args.require_int(env.args, '--timeout', minval=0)
    base = args.require_int(env.args, '--start-port', minval=0, maxval=65535)
    nports = args.require_int(env.args, '--num-ports', minval=0, maxval=1000)

    candidates = get_port_candidates([port], base, nports)
    endpoints = find_external_endpoints([port], candidates, timeout)

    if not endpoints:
        sys.exit(1)

    endpoint = endpoints[port]
    print('{}:{}'.format(*endpoint))
