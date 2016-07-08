#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='bootstrap_salt',
    version='1.3.1',
    url='http://github.com/ministryofjustice/bootstrap-salt/',
    license='LICENSE',
    author='MOJDS',
    author_email='tools@digital.justice.gov.uk',
    description='MOJDS salt bootstrap tool',
    long_description="",
    include_package_data=True,
    packages=find_packages(exclude=["tests"]),
    zip_safe=False,
    platforms='any',
    test_suite='tests',
    install_requires=[
        'Fabric>=1.10.1',
        'PyYAML>=3.11',
        'boto>=2.36.0',
        'bootstrap-cfn>=0.5.7',
        'requests',
        'ndg-httpsclient',
        'dnspython',
        'awscli',
        'gnupg'
    ],
    setup_requires=[
        'mock>=1.0.1',
        'testfixtures>=4.1.2',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
