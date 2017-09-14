#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from pip.req import parse_requirements

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')
requirements = parse_requirements("requirements.txt", session=False)

setup(
    name='nectar_tools',
    version='0.1.0',
    description=('A collection of useful tools for operating the '
                 'NeCTAR Research Cloud'),
    long_description=readme + '\n\n' + history,
    author='Kieran Spear',
    author_email='kispear@gmail.com',
    url='https://github.com/NeCTAR-RC/nectar-tools',
    packages=[
        'nectar_tools',
    ],
    package_dir={'nectar_tools':
                 'nectar_tools'},
    entry_points={
        'console_scripts': [
            'nectar-pt-expiry = nectar_tools.expiry.cmd.pt_expirer:main',
            'nectar-allocation-expiry = nectar_tools.expiry.cmd.allocation_expirer:main',
            'nectar-allocation-provisioner = nectar_tools.provisioning.cmd.provision:main',
        ],
    },
    include_package_data=True,
    install_requires=[str(r.req) for r in requirements],
    license="GPLv3+",
    zip_safe=False,
    keywords='nectar_tools',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        ('License :: OSI Approved :: '
         'GNU General Public License v3 or later (GPLv3+)'),
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
)
