#
# This file is part of ravstack. Ravstack is free software available under
# the terms of the MIT license. See the file "LICENSE" that was provided
# together with this source file for the licensing terms.
#
# Copyright (c) 2015 the ravstack authors. See the file "AUTHORS" for a
# complete list.

from __future__ import absolute_import, print_function

from invoke import run, task


@task
def clean():
    run('find . -name __pycache__ | xargs rm -rf || :', echo=True)
    run('find . -name \*.pyc | xargs rm -f', echo=True)
    run('find . -name \*.egg-info | xargs rm -rf', echo=True)
    run('rm -rf build dist', echo=True)


@task
def checksdist():
    from setup import version_info
    run('git ls-files | sort > files.git')
    run('rm -rf lib/*.egg-info')
    run('python setup.py sdist >/dev/null 2>&1')
    run('tar tfz dist/{name}-{version}.tar.gz'
       ' | sed -e \'s/^{name}-{version}\///\' -e \'/\/$/d\' -e \'/^$/d\''
       ' | sort > files.sdist'.format(**version_info))
    run('diff -u files.git files.sdist || true')
    run('rm files.git; rm files.sdist')
