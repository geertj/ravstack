#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function


def require_int(args, name, minval=None, maxval=None, default=None):
    if isinstance(args, dict):
        value = args.get(name, default)
    else:
        value = args
    if value is None:
        raise RuntimeError('Missing argument `{}`.'.format(name))
    if not value.isdigit():
        raise RuntimeError('Argument `{}` must be integer.'.format(name))
    value = int(value)
    if minval is not None and value < minval:
        raise RuntimeError('Argument `{}` must be at least {}.'.format(minval))
    if maxval is not None and value > maxval:
        raise RuntimeError('Argument `{}` must be at most {}.'.format(maxval))
    return value
