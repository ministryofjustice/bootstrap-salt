#!/bin/bash -xe

# SETUP EC2 INSTANCE
T1=`dpkg -l | grep python-setuptools | wc -l`
T2="1"
if [ "$T1" = "$T2" ]; then
  echo "[INFO] Base packages already installed..."
else
  apt-get update
  apt-get -y install python-setuptools git
  easy_install boto
fi

# get bootstrap-salt, doesn't do upgrade anymore
if [ -d "/usr/local/bootstrap-salt" ]; then
  echo "[INFO] boostrap-salt already installed..."
else
  cd /usr/local && git clone https://github.com/ministryofjustice/bootstrap-salt
  easy_install https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-latest.tar.gz
  chmod 755 /usr/local/bootstrap-salt/scripts/ec2_tags.py
  chmod 750 /usr/local/bootstrap-salt/bootstrap_salt/salt_utils.py
  chmod 750 /usr/local/bootstrap-salt/bootstrap_salt/salt_utils_update.py
  chmod 750 /usr/local/bootstrap-salt/bootstrap_salt/salt_utils_state.py
  /usr/local/bootstrap-salt/scripts/ec2_tags.py
fi
