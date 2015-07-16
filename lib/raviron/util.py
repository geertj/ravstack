#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

import os
import pwd
import errno
import socket
import struct
import re


def get_homedir():
    """Return the user home directory."""
    home = os.environ.get('HOME')
    if home is None:
        pw = pwd.getpwuid(os.getuid())
        home = pw.pw_dir
    return home

def get_user():
    """Return the current user name."""
    user = os.environ.get('LOGNAME')
    if user is None:
        pw = pwd.getpwuid(os.getuid())
        user = pw.pw_name
    return user


def create_directory(dirname, mode=0o755):
    """Create a new directory."""
    try:
        os.mkdir(dirname, mode)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def try_stat(fname):
    """Call `os.stat(fname)`. Return the stat result, or `None` if the file
    does not exist."""
    try:
        return os.stat(fname)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def can_open(fname, mode='r'):
    """Return whether file *fname* is writable by us."""
    try:
        with open(fname, mode):
            return True
    except IOError as e:
        if e.errno not in (errno.ENOENT, errno.EACCES):
            raise
        return False


def mask_dict(d, *names):
    """Mask certain values in a dict."""
    m = {}
    for k, v in d.items():
        m[k] = '****' if k in names else v
    return m


_re_field = re.compile(r'\{[^}]*\}')

def unique_name_seqno(template, names):
    """Return a new unique name based on a template."""
    re_seqno = re.compile(_re_field.sub('([0-9]+)', template))
    maxseq = 0
    for name in names:
        match = re_seqno.match(name)
        if not match:
            continue
        maxseq = max(maxseq, int(match.group(1)))
    return template.format(maxseq + 1)


def inet_aton(s):
    """Like `socket.inet_aton()` but returns an int."""
    packed = socket.inet_aton(s)
    return struct.unpack('!I', packed)[0]

def inet_ntoa(i):
    """Like `socket.inet_nota()` but accepts an int."""
    packed = struct.pack('!I', i)
    return socket.inet_ntoa(packed)
