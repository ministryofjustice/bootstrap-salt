## Version unreleased

* Sync salt_utils script with every rsync.

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
