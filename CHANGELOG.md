## Version 1.1.2

* Fix bug in `upload_salt` fab task that where you would get an OSError if you
  had created any files in your projects ./salt/_grain folder.

## Version 1.1.1

* Change how we produce the "salt.tar" so that it is both simpler and platform
  agnostic
* Place a salt minion config file so that we look for files in /srv/salt and
  /srv/salt-formulas

## Version 1.1.0

* Provide a wrapped `cfn_delete` task that will remove the managed
  salt.tar.gpg so that when we make the DeleteStack API call it doesn't error
  saying the bucket is not empty.

## Version 1.0.2

* Fix running individual states with salt_util

## Version 1.0.1

* Fix installing contrib files to correct path.

## Version 1.0.0

* Removing salt-master. This now bootstraps by uploading content to S3. This makes it possible for instances to pull content from S3 when they are created without interaction.

## Version 0.2.2

* Make it possible to create multiple stacks with the same app and env.

## Version 0.2.1

* Bug fix: missing keyword in get_stack_instances breaks salt.setup

## Version 0.2.0

* Make it possible to target minions in batches by passing a decimal fraction to the salt_utils script.
* Upgrade salt to 2014.7.4
* Make salt version an argument
* Add docstrings to fab tasks
* Bug fix: search only running instances

## Version 0.1.2

* Bug fix: import the correct config from bootstrap_cfn

## Version 0.1.1

* Sync salt_utils script with every rsync.
* Generate SSH keys from Github.
* Bug fix: salt would only install on the master

## Version 0.1.0

First release to PyPi

* Bug fix: Install boto at salt-bootstrap time.

  Without this tags_to_grains wouldn't work which meant that the EC2 tags were
  not available as grains on the box which caused things to fail in odd ways


## Version 0.0.6

* Remove tag script
* Fix instance type comparison bug
* Add DNS records when creating salt master

## Version 0.0.5

* Add validation for the environment variables when calling rsync

## Version 0.0.4

* Fixes a bug in find_master which can cause it to find the wrong master. Highly recommended update.

## Version 0.0.1

A **very** rough cut of everything salt specific from bootstrap_cfn. This will
need lots of things removing from this repo too.
