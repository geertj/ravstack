#
# This file is part of Raviron. Raviron is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the Raviron authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

from setuptools import setup


version_info = {
    'name': 'raviron',
    'version': '0.9.dev0',
    'description': 'OpenStack Ironic power control for Ravello Systems',
    'author': 'Geert Jansen',
    'author_email': 'geertj@gmail.com',
    'url': 'https://github.com/geertj/raviron',
    'license': 'MIT',
    'classifiers': [
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4'
    ]
}

setup(
    packages=['raviron'],
    entry_points={
        'console_scripts': [
            'create-key = raviron.keys:main',
            'proxy-cmd = raviron.proxy:main']},
    **version_info)
