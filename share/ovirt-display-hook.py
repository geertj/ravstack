#!/usr/bin/env python
#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

# This is a VDSM hook that maps internal display IP addresses and port numbers
# to their externally available endpoints. You need to install this hook in
# /usr/libexec/vdsm/hooks for the following events:
#
# * after_get_vm_stats
# * after_get_all_vm_stats
#
# This hook depends on ravstack, so you need to install that first, and then
# copy this file to the above two directories.

from __future__ import absolute_import, print_function

import os
import sys
import time
import hooking
import tempfile
import errno
import json

from ravstack.endpoint import find_external_endpoints, get_port_candidates

_cache_ttl = 60
_cache_file = '/var/run/vdsm/endpoints.json'


def debug(message, *args):
    """Write a debug message. The message ends up in vdsm.log."""
    if args:
        message = message.format(*args)
    sys.stderr.write('DEBUG [ovirt-display-hook]: {}\n'.format(message))


def load_cache():
    """Load the port mapping cache."""
    try:
        with open(_cache_file) as fin:
            entries = json.loads(fin.read())
        return dict(((entry['local'], entry) for entry in entries))
    except IOError as e:
        if e.errno == errno.ENOENT:
            return {}
        raise


def update_cache(cache, endpoints):
    """Update the cache with freshly discovered endpoints."""
    now = int(time.time())
    for port, addr in endpoints.items():
        cache[port] = {'local': port, 'ip': addr[0], 'port': addr[1], 'timestamp': now}


def try_unlink(fname):
    """Try to unlink a file but do not raise an error if the file does not
    exist."""
    try:
        os.unlink(fname)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def save_cache(cache):
    """Save the cache back to disk."""
    entries = list(cache.values())
    fd, tmpname = tempfile.mkstemp(dir=os.path.split(_cache_file)[0])
    try:
        with os.fdopen(fd, 'w') as fout:
            fout.write(json.dumps(entries, sort_keys=True, indent=2))
            fout.write('\n')
        os.chmod(tmpname, 0o644)
        os.rename(tmpname, _cache_file)
    finally:
        try_unlink(tmpname)


def main():
    """Main entry point."""
    cache = load_cache()
    stats = hooking.read_json()

    # Get a list of the ports we need to map.

    ports = []
    for st in stats:
        for disp in st.get('displayInfo', []):
            port = int(disp.get('port', '0'))
            if port > 0:
                ports.append(port)
            port = int(disp.get('tlsPort', '0'))
            if port > 0:
                ports.append(port)

    debug('ports to be mapped: {}', ', '.join(map(str, ports)))

    # Assess the status of the cache with respect to our ports.

    fresh = complete = True
    now = time.time()

    for port in ports:
        if port not in cache:
            fresh = complete = False
            break
        entry = cache[port]
        if now - entry['timestamp'] > _cache_ttl:
            fresh = False
            break

    debug('cache state: fresh = {}, complete = {}', fresh, complete)

    # If we are not fresh but we are complete then we can try just to scan the
    # ports of the previously discovered endpoints as an optimization. These
    # should not normally change.

    if not fresh and complete:
        debug('cache is complete so try previous endpoints')
        candidates = [cache[port]['port'] for port in ports]
        debug('port candidates are: {}', ', '.join(map(str, candidates)))
        endpoints = find_external_endpoints(ports, candidates)
        update_cache(cache, endpoints)
        if len(endpoints) == len(ports):
            complete = True

    # If we are not complete at this point, then we do a scan over the full port
    # mapping range.

    if not complete:
        debug('cache is not complete so scan full port mapping range')
        candidates = get_port_candidates(ports)
        debug('port candidates are: {}', ', '.join(map(str, candidates)))
        endpoints = find_external_endpoints(ports, candidates)
        update_cache(cache, endpoints)
        if len(endpoints) == len(ports):
            complete = True

    debug('new cache state: complete = {}', complete)

    # We are either complete or we aren't. Map as much as we can.

    for st in stats:
        for disp in st.get('displayInfo', []):
            debug('displayInfo: {!r}', disp)
            port = int(disp.get('port', '0'))
            if port in cache:
                entry = cache[port]
                disp['port'] = str(entry['port'])
                disp['ipAddress'] = entry['ip']
                debug('port {} mapped to {}:{}', port, entry['ip'], entry['port'])
            elif port > 0:
                debug('port {} could not be mapped', port)
            port = int(disp.get('tlsPort', '0'))
            if port in cache:
                entry = cache[port]
                disp['tlsPort'] = str(entry['port'])
                disp['ipAddress'] = entry['ip']
                debug('tlsPort {} mapped to {}:{}', port, entry['ip'], entry['port'])
            elif port > 0:
                debug('tlsPort {} could not be mapped', port)

    save_cache(cache)
    hooking.write_json(stats)


if __name__ == '__main__':
    main()
