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

    fab application:courtfinder aws:prod environment:dev config:/path/to/courtfinder-dev.yaml salt.setup

- **application:courtfinder** - should match the name given to bootstrap-cfn
- **aws:dev** - is a way to differentiate between AWS accounts ``(~/.config.yaml)``
- **environment:dev** - should match the environment given to bootstrap-cfn
- **config:/path/to/file.yaml** - The location to the project YAML file

Multiple Stacks
=================

If you want to run multiple stacks with the same name, ensure that you specify a zone for the salt master DNS records in the yaml config::

    master_zone:
      my-zone.dsd.io

Then when you create a stack you can specify a tag before cfn_create, like::

    fab application:courtfinder aws:my_project_prod environment:dev config:/path/to/courtfinder-dev.yaml tag:active cfn_create salt.setup

NB active is the default.

Then you can refer to this stack by it's tag in the future. In this way it is easier to bring up two stacks from the same config. If you want to swap the names of the stacks you can do the following::

    fab application:courtfinder aws:my_project_prod environment:dev config:/path/to/courtfinder-dev.yaml swap_tags:inactive,active salt.swap_masters:inactive,active

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

Salt master DNS
++++++++++++++++
This tool will attempt to create a DNS entry for the salt master during the bootstrap process. You must specify the zone in which to create the entry in the bootstrap-cfn config file like so::

    master_zone: myzone.dsd.io

If you do not specify a zone, then no entry will be created and you will need AWS credentials as above to discover the master when deploying etc.

The entry created will be::

    master.<environment>.<application>.<master_zone>

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

Github based SSH key generation
+++++++++++++++++++++++++++++++
To add individual users to the AWS stack.

1. to customize the list of users, teams and keys, add the following to the project
   YAML template; it offers more flexibility: for example multiple keys per user, or limiting
   to specific keys for users with multiple keys:

::


    myenv:
      github_users:
        ministryofjustice: # or any org
          individuals:
            - koikonom:
                fingerprints:
                  - '35:53:6f:27:fe:39:8b:d8:dd:87:19:f3:40:d2:84:6a'
                unix_username:
                  kyriakos
            - ashb:
                fingerprints:
                  - '0c:11:2b:78:ff:8d:5f:f0:dc:27:8e:e2:f8:2f:ab:25'
                  - 'af:e0:6c:dc:bd:9b:bf:1d:9b:de:2d:de:12:6e:f2:8a'
            - mattmb
          teams:
            - some-team-name
              - some-user:
                  unix_username: userunixusername
                  fingerprints: 00:11:22:33:44:55:66
            - anotherteam

2. in the simplest version, just add the list of teams (all users' keys will be used) 
   to the projec YAML template

::


    github_users:
      ministryofjustice: # or any org
        teams:
          - webops
          - crime-billing-online


3. if a team doesn't exist, create it on GitHub granting "Read" access. Example of a team:
    https://github.com/orgs/ministryofjustice/teams/webops
    

4. obtain a GitHub token and set the GH_TOKEN variable in your environment:
    https://help.github.com/articles/creating-an-access-token-for-command-line-use/

5. run the following command:

::


    fab application:<yourapp> aws:<your_aws_profile> environment:myenv config:<your template yaml file> ssh_keys


6. the above command, if succesful, creates the file 
   :code:`pillar/<myenv>/keys.sls`  (can be renamed, often as :code:`admins.sls`)
   
   Add an entry with the name of this file to 
   :code:`pillar/<myenv>/top.sls`


::


       base:
         'Env:demo':
           - match: grain
           - demo
           - demo-secrets
           - cloudformation
           - admins

7. highstate the stack
