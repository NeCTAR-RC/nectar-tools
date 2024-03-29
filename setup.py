#!/usr/bin/env python

import setuptools

from pbr.packaging import parse_requirements


readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')


setuptools.setup(
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
            'nectar-allocation-audit = nectar_tools.audit.cmd.allocation:main',
            'nectar-allocation-expiry = nectar_tools.expiry.cmd.allocation_expirer:main',  # noqa
            'nectar-allocation-instance-expiry = nectar_tools.expiry.cmd.allocation_instance_expirer:main',  # noqa
            'nectar-allocation-provisioner = nectar_tools.provisioning.cmd.provision:main',  # noqa
            'nectar-allocation-reset-quotas = nectar_tools.provisioning.cmd.reset_quotas:main',  # noqa
            'nectar-app-audit = nectar_tools.audit.cmd.app_catalog:main',
            'nectar-compute-audit = nectar_tools.audit.cmd.compute:main',
            'nectar-database-audit = nectar_tools.audit.cmd.database:main',
            'nectar-dns-audit = nectar_tools.audit.cmd.dns:main',
            'nectar-identity-audit = nectar_tools.audit.cmd.identity:main',
            'nectar-image-expiry = nectar_tools.expiry.cmd.image_expirer:main',
            'nectar-account-expiry = nectar_tools.expiry.cmd.account_expirer:main',  # noqa
            'nectar-image-audit = nectar_tools.audit.cmd.image:main',
            'nectar-network-audit = nectar_tools.audit.cmd.network:main',
            'nectar-metric-audit = nectar_tools.audit.cmd.metric:main',
            'nectar-placement-audit = nectar_tools.audit.cmd.placement:main',
            'nectar-coe-audit = nectar_tools.audit.cmd.coe:main',
            'nectar-loadbalancer-audit = nectar_tools.audit.cmd.loadbalancer:main',  # noqa
            'nectar-project-allocation-audit = nectar_tools.audit.cmd.project:main',  # noqa
            'nectar-pt-audit = nectar_tools.audit.cmd.pt:main',
            'nectar-pt-expiry = nectar_tools.expiry.cmd.pt_expirer:main',
            'nectar-rating-audit = nectar_tools.audit.cmd.rating:main',
            'nectar-su-reports = nectar_tools.reports.cmd.su_report:main',  # noqa
            'resource-capacity = nectar_tools.cli.resource_capacity:main',
            'send-fd-outbound = nectar_tools.cli.send_fd_outbound:main',
            'nectar-trove-upgrade-notifier = nectar_tools.cli.trove_datastore_upgrades:main',  # noqa
            'warre-maintenance = nectar_tools.cli.warre_maintenance:main',
            'warre-host-flavors = nectar_tools.cli.warre_host_flavors:main',
        ],
    },
    include_package_data=True,
    install_requires=parse_requirements(),
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
