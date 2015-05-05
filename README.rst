.. image:: https://travis-ci.org/ministryofjustice/bootstrap-salt.svg?branch=master
    :target: https://travis-ci.org/ministryofjustice/bootstrap-salt?branch=master

.. image:: https://coveralls.io/repos/ministryofjustice/bootstrap-salt/badge.svg?branch=master
    :target: https://coveralls.io/r/ministryofjustice/bootstrap-salt?branch=master

Ministry of Justice - Bootstrap Salt
====================================

The aim of this repos is to provide a standard way to bootstrap salt master and minions in an AWS environment. Currently it depends on `bootstrap-cfn <https://github.com/ministryofjustice/bootstrap-cfn>`_

It exposes a fabric task called ``salt.setup`` which will elect a master from an Auto Scaling Group (ASG) and install minions on any other members of the ASG.

Installation
=============
::

    git clone git@github.com:ministryofjustice/bootstrap-salt.git
    cd bootstrap-salt
    pip install -r requirements.txt


Developing and running tests
=============================

The test suite can be run via setup.py as follows::

    python -m unittest discover

or::

    python setup.py test

Example Usage
==============

Bootstrap-salt uses `fabric <http://www.fabfile.org/>`_

If you also want to bootstrap the salt master and minions, you can do this::

    fab application:app-name aws:dev environment:dev config:/path/to/app-name-dev-config.yaml salt.setup

- **application:app-name** - should match the name given to bootstrap-cfn
- **aws:dev** - is a way to differentiate between AWS accounts ``(~/.config.yaml)``
- **environment:dev** - should match the environment given to bootstrap-cfn
- **config:/path/to/app-name-dev-config.yaml** - The location to the project YAML file

Example Configuration
======================
AWS Account Configuration
++++++++++++++++++++++++++

This tool needs AWS credentials to create stacks and the credentials should be placed in the ``~/.aws/credentials`` file (which is the same one used by the AWS CLI tools). You should create named profiles like this (and the section names should match up with what you specify to the fabric command with the ``aws:my_project_prod`` flag) ::


    [my_project_dev]
    aws_access_key_id = AKIAI***********
    aws_secret_access_key = *******************************************
    [my_project_prod]
    aws_access_key_id = AKIAI***********
    aws_secret_access_key = *******************************************

If you wish to authenticate to a separate AWS account using cross account IAM roles you should create a profile called `cross-account` with the access keys of the user with permission to assume roles from the second account::

    [cross-account]
    aws_access_key_id = AKIAI***********
    aws_secret_access_key = *******************************************

And when you run the tool you must set the ARN ID of the role in the separate account which you wish to assume. For example::

    AWS_ROLE_ARN_ID='arn:aws:iam::123456789012:role/S3Access' fab application:courtfinder aws:prod environment:dev config:/path/to/courtfinder-dev.yaml salt.setup

Salt specific configuration
++++++++++++++++++++++++++++

In order to rsync your salt states to the salt master you need to add a `salt` section to the top level of your project's YAML file. The following parameters specify the rsync sources and targets:

- **local_salt_dir**: Directory containing all the files you want to have in your salt root (for example top.sls or project specific states).
    **Default value**: ./salt
- **local_pillar_dir**: Directory containing all the files you want to have in your pillar root.
    **Default value**: ./pillar
- **local_vendor_dir**: Directory containing formulas cloned by salt-shaker.
    **Default value**: ./vendor
- **remote_state_dir**: Salt root on the master.
    **Default value**: /srv/salt
- **remote_pillar_dir**: Pillar root on the master.
    **Default value**: /srv/pillar

The cloudformation yaml will be automatically uploaded to your pillar as cloudformation.sls. So if you include ``-cloudformation`` in your pillar top file you can do things like:

::

    salt-call pillar.get s3:static-bucket-name
