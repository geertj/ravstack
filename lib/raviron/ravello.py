#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

from requests import Session, HTTPError
from requests.adapters import HTTPAdapter


class RavelloApi(Session):
    """
    A super minimal interface to the Ravello API, based on ``requests.Session``.
    """

    default_url = 'https://cloud.ravellosystems.com/api/v1'
    default_timeout = (10, 60)
    default_retries = 3
    default_redirects = 3

    def __init__(self):
        super(RavelloApi, self).__init__()
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
        return super(RavelloApi, self).request(method, url, **kwargs)

    def call(self, method, url, body=None, **kwargs):
        if body is not None:
            kwargs['json'] = body
        r = self.request(method, url, **kwargs)
        self._raise_for_status(r)
        if not r.content:
            return  # Allow empty responses -> None
        return r.json()


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
