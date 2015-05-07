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
