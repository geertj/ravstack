#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

__all__ = ['urlparse']

# The six version shipped with CentOS 7 is too old. It doesn't have
# six.moves.urllib.parse.

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
