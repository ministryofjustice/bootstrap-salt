#!/bin/bash
wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/6080a18e6c7c2d49335978fa69fa63645b45bc2a/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh
chmod 700 /tmp/bootstrap-salt.sh
apt-get update && apt-get -y install python-pip git python-dev
pip install boto
pip install gnupg
cd /tmp
git clone https://github.com/ministryofjustice/bootstrap-salt.git
cd ./bootstrap-salt
git checkout $BOOTSTRAP_SALT_REV
cp -Lrf ./contrib/* /
/tmp/bootstrap-salt.sh git v2014.7.5
salt-call saltutil.sync_all
/usr/local/bin/salt_utils.py -s highstate
touch /tmp/bootstrap_done
