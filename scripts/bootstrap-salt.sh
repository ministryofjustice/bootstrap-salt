#!/bin/bash -xe

# SETUP EC2 INSTANCE
apt-get update
apt-get -y install python-setuptools git
easy_install boto

# get or update bootstrap-salt
if [ -d "/usr/local/bootstrap-salt" ]; then
  cd /usr/local/bootstrap-salt && git pull
else
  cd /usr/local && git clone https://github.com/ministryofjustice/bootstrap-salt
fi

easy_install https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-latest.tar.gz
chmod 755 /usr/local/bootstrap-salt/scripts/ec2_tags.py
chmod 750 /usr/local/bootstrap-salt/bootstrap_salt/salt_utils.py
/usr/local/bootstrap-salt/scripts/ec2_tags.py

