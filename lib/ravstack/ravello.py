#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import time
import logging
import random
import json

from requests import Session, HTTPError
from requests.adapters import HTTPAdapter

LOG = logging.getLogger(__name__)

magic_svm_cpuids = [
    {"index": "0", "value": "0000000768747541444d416369746e65"},
    {"index": "1", "value": "000006fb00000800c0802000078bfbfd"},
    {"index": "8000000a", "value": "00000001000000400000000000000089"},
    {"index": "80000000", "value": "8000000a000000000000000000000000"},
    {"index": "80000001", "value": "00000000000000000000001520100800"}, ]


class RavelloClient(Session):
    """
    A super minimal interface to the Ravello API, based on ``requests.Session``.
    """

    default_url = 'https://cloud.ravellosystems.com/api/v1'
    default_timeout = (10, 60)
    default_retries = 3
    default_redirects = 3

    def __init__(self):
        super(RavelloClient, self).__init__()
        self.headers['Accept'] = 'application/json'
        self.max_redirects = self.default_redirects
        adapter = HTTPAdapter(max_retries=self.default_retries)
        self.mount('http://', adapter)
        self.mount('https://', adapter)
        self.user_info = None

    def _raise_for_status(self, r):
        """Raise an exception if *resp* is an error response."""
        if 400 <= r.status_code < 500:
            message = 'Client Error: '
        elif 500 <= r.status_code < 600:
            message = 'Server Error: '
        else:
            return
        method = r.request.method
        url = r.url
        if url.startswith(self.default_url):
            url = url[len(self.default_url):]
        message += '{} {} for `{} {}`.'.format(r.status_code, r.reason, method, url)
        err_code = r.headers.get('Error-Code')
        if err_code:
            err_message = r.headers.get('Error-Message', '')
            message += ' ({}: {})'.format(err_code, err_message)
        raise HTTPError(message, response=r)

    def login(self, username, password):
        """Login to the API."""
        resp = self.request('POST', '/login', auth=(username, password))
        self._raise_for_status(resp)
        self.user_info = resp.json()
        self.cookies = resp.cookies

    def logout(self):
        self.request('POST', '/logout')
        self.cookies.clear()

    def request(self, method, url, **kwargs):
        if url.startswith('/'):
            url = self.default_url + url
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.default_timeout
        return super(RavelloClient, self).request(method, url, **kwargs)

    def call(self, method, url, body=None, **kwargs):
        if body is not None:
            kwargs['json'] = body
        r = self.request(method, url, **kwargs)
        self._raise_for_status(r)
        if not r.content:
            return  # Allow empty responses -> None
        return r.json()


class Retry(RuntimeError):
    """Exception used to indicate to retry_operation() that it needs to
    retry."""


_default_retries = {409: 10}

def retry_operation(func, timeout=60, retries=None):
    """Retry an operation on various 4xx errors."""
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
            ret = func()
        except HTTPError as e:
            status = e.response.status_code
            if status not in retries:
                raise
            LOG.debug('Retry: {!s}'.format(e))
            tries.setdefault(status, 0)
            tries[status] += 1
            if not 0 < tries[status] < retries[status]:
                LOG.error('Max retries reached for status {} ({})'
                                .format(status, retries[status]))
                raise
            LOG.warning('Retry number {} out of {} for status {}.'
                            .format(tries[status], retries[status], status))
        except Retry as e:
            LOG.warning('Retry requested: {}.'.format(e))
        else:
            time_spent = time.time() - start_time
            LOG.debug('Operation succeeded after {} attempt{} ({:.2f} seconds).'
                            .format(count, 's' if count > 1 else '', time_spent))
            return ret
        loop_delay = delay + random.random()
        LOG.debug('Sleeping for {:.2f} seconds.'.format(loop_delay))
        time.sleep(loop_delay)
    time_spent = time.time() - start_time
    raise RuntimeError('Timeout retrying function `{.__name__}` ({:.2f} seconds).'
                        .format(func, time_spent))


def simple_filter(**kwargs):
    """Return a simple filter that requires all keyword arguments to be equal
    to their specified value."""
    criteria = []
    for key, value in kwargs.items():
        criteria.append({'type': 'SIMPLE', 'propertyName': key,
                         'operator': 'Equals', 'operand': value})
    return {'type': 'COMPLEX', 'operator': 'And', 'criteria': criteria}


_sizes = {'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}

def convert_size(size, unit):
    """Convert a memory size with one unit to another unit."""
    return size['value'] * _sizes[size['unit']] // _sizes[unit]


def get_vms(app, scope='deployment'):
    """Return the VMs in an application."""
    return app.get(scope, {}).get('vms', [])


def get_network(vm, ip):
    """Return the network with an IP *ip*."""
    for conn in vm.get('networkConnections', []):
        if get_ip(conn) == ip:
            return conn


def get_ip(conn):
    """Return the primary IP of a network connection."""
    ipcfg = conn.get('ipConfig')
    if not ipcfg:
        return
    stcfg = ipcfg.get('staticIpConfig')
    aucfg = ipcfg.get('autoIpConfig')
    if stcfg:
        return stcfg.get('ip')
    elif aucfg:
        ip = aucfg.get('allocatedIp')
        if ip is None:
            ip = aucfg.get('reservedIp')
        return ip


def get_mac(conn):
    """Return the Mac address for a network connection."""
    dev = conn.get('device')
    if dev is None:
        return
    mac = dev.get('mac')
    if mac is None:
        mac = dev.get('generatedMac')
    return mac


def get_service(vm, port):
    """Return the service for a given port."""
    for service in vm.get('suppliedServices', []):
        if service['portRange'] == port:
            return service


def get_injected_metadata():
    """Return the injected metadata from /etc/ravello."""
    try:
        with open('/etc/ravello/vm.json') as fin:
            meta = json.loads(fin.read())
    except IOError:
        return {}
    return meta
