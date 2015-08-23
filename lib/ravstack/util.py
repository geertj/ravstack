#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
import pwd
import errno
import socket
import struct
import subprocess
import locale
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


def try_unlink(fname):
    """Try to unlink a file but do not raise an error if the file does not
    exist."""
    try:
        os.unlink(fname)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def mask_dict(d, *names):
    """Mask certain values in a dict."""
    m = {}
    for k, v in d.items():
        m[k] = '****' if k in names else v
    return m


def filter_dict(d, *keys):
    """Filter keys from a dictionary."""
    f = {}
    for k, v in d.items():
        if k in keys:
            f[k] = v
    return f


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


def parse_env_file(filename, pattern):
    """Source a shell script and extract variables from it."""
    # Use the shell to parse this so we can also read substitutions
    # like $() for example.
    env = {}
    command = 'source {}; set | grep -E "{}"'.format(filename, pattern)
    output = subprocess.check_output(['sh', '-c', command])
    output = output.decode(locale.getpreferredencoding())
    for line in output.splitlines():
        p1 = line.find('=')
        env[line[:p1]] = line[p1+1:]
    return env


def run_ssh(addr, command, **kwargs):
    """Run a command over SSH and return the output."""
    encoding = locale.getpreferredencoding()
    if kwargs.get('input'):
        kwargs['input'] = kwargs['input'].encode(encoding)
    if isinstance(command, str):
        command = [command]
    cmdargs = ['ssh', '-T', '-o', 'StrictHostKeyChecking=no', addr] + command
    output = subprocess.check_output(cmdargs, **kwargs)
    return output.decode(encoding)


def can_run_sudo(command='/bin/sh', user='root'):
    """Check whether the current user is allowed to run sudo."""
    if isinstance(command, str):
        command = [command]
    cmdargs = ['sudo', '-n', '-u', user, '-l'] + command
    ret = subprocess.call(cmdargs, stdout=subprocess.DEVNULL)
    return ret == 0


def run_sudo(command, user='root', **kwargs):
    """Run a command through sudo and return the output."""
    encoding = locale.getpreferredencoding()
    if kwargs.get('input'):
        kwargs['input'] = kwargs['input'].encode(encoding)
    if isinstance(command, str):
        command = [command]
    cmdargs = ['sudo', '-u', user] + command
    output = subprocess.check_output(cmdargs, **kwargs)
    return output.decode(encoding)


def selinux_enabled():
    """Return whether selinux is enabled."""
    encoding = locale.getpreferredencoding()
    try:
        output = subprocess.check_output(['getenforce'])
    except subprocess.CalledProcessError:
        return False
    output = output.decode(encoding).strip().lower()
    return output in ('permissive', 'enforcing')
