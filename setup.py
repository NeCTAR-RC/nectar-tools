#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

try: # for pip >= 10
    from pip._internal.req import parse_requirements
except ImportError: # for pip <= 9.0.3
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
    author='Sam Morrison',
    author_email='sorrison@gmail.com',
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
            'nectar-pt-audit = nectar_tools.audit.cmd.pt:main',
            'nectar-allocation-audit = nectar_tools.audit.cmd.allocation:main',
            'nectar-project-allocation-audit = nectar_tools.audit.cmd.project:main',
            'nectar-identity-audit = nectar_tools.audit.cmd.identity:main',
            'nectar-metric-audit = nectar_tools.audit.cmd.metric:main',
            'nectar-compute-audit = nectar_tools.audit.cmd.compute:main',
            'nectar-dns-audit = nectar_tools.audit.cmd.dns:main',
            'nectar-app-audit = nectar_tools.audit.cmd.app_catalog:main',
            'nectar-placement-audit = nectar_tools.audit.cmd.placement:main',
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
