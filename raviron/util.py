#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

import os
import sys
import pwd
import errno
import stat
import getpass
import functools
import logging
import re


def get_debug():
    """Return whether debugging is requested."""
    return os.environ.get('DEBUG', '0') not in ('0', 'n')

def set_debug(enabled=True):
    """Enable debugging."""
    os.environ['DEBUG'] = '1' if enabled else '0'


_memodata = {}

def memoize(func):
    """Memoizes a function.
    
    Note: ignores function arguments when memoizing.
    """
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        key = getattr(func, '__qualname__', func.__name__)
        if key not in _memodata:
            _memodata[key] = func(*args, **kwargs)
        return _memodata[key]
    return wrapped


@memoize
def get_homedir():
    """Return the user home directory."""
    home = os.environ.get('HOME')
    if home is None:
        pw = pwd.getpwuid(os.getuid())
        home = pw.pw_dir
    return home


def create_directory(dirname, mode=0o755):
    """Create a new directory."""
    try:
        st = os.mkdir(dirname, mode)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def make_executable(fname):
    """Make a file executable for everyone that has read access to it."""
    st = os.stat(fname)
    new_mode = st.st_mode & 0o777
    if new_mode & stat.S_IRUSR:
        new_mode |= stat.S_IXUSR
    if new_mode & stat.S_IRGRP:
        new_mode |= stat.S_IXGRP
    if new_mode & stat.S_IROTH:
        new_mode |= stat.S_IXOTH
    os.chmod(fname, new_mode)


_re_field = re.compile(r'\{[^}]+\}')

def create_unique_file_seqno(dirname, template, mode=0o755):
    """Return a new unique file based on a prefix and a sequence number.

    Return the file name and the sequence number allocated.
    """
    re_seqno = re.compile(_re_field.sub('([0-9]+)', template))
    maxseq = 0
    for entry in os.listdir(dirname):
        match = re_seqno.match(entry)
        if not match:
            continue
        maxseq = max(maxseq, int(match.group(1)))
    seqno = maxseq + 1
    while True:
        fname = os.path.join(dirname, template.format(seqno))
        try:
            fd = os.open(fname, os.O_CREAT|os.O_EXCL, mode)
            break
        except IOError as e:
            if e.errno != errno.EEXIST:
                raise
        finally:
            os.close(fd)
        seqno += 1
    return seqno, fname


@memoize
def setup_logging():
    homedir = get_homedir()
    logdir = os.path.join(homedir, 'logs')
    create_directory(logdir)
    logfile = os.path.join(logdir, 'raviron.log')
    logger = logging.getLogger()
    handler = logging.FileHandler(logfile)
    logger.addHandler(handler)
    template = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    handler.setFormatter(logging.Formatter(template))
    logger.setLevel(logging.DEBUG)

def get_logger(context=''):
    """Return the application logger."""
    setup_logging()
    logger = logging.getLogger('raviron')
    # TODO: add context
    return logger
