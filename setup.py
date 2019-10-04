#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name='snow',
    version='0.0.1',  # Required
    packages=['snow', 'snow.util'],
    url='https://github.com/UoA-eResearch/snow.git',
    description='service now cli',
    long_description=open('README.md').read(),
    install_requires=[
        "requests",
        'beautifulsoup4',
        'tabulate',
        'python-editor',
        'click',
        'html5lib',
        ],
    include_package_data=True,
)

# vim: fenc=utf-8: ft=python:sw=4:et:nu:fdm=indent:fdn=1:syn=python

