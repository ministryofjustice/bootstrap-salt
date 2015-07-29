import json
import pkg_resources
import unittest

import bootstrap_salt.config
from bootstrap_salt.config import MyConfigParser

from mock import patch

from testfixtures import compare
from troposphere import Template


class TestConfig(unittest.TestCase):

    def setUp(self):
        pass

    # http://mock.readthedocs.org/en/latest/patch.html#where-to-patch
    @patch('bootstrap_salt.config.ConfigParser.base_template')
    @patch.object(bootstrap_salt.config, 'env')
    def test_base_template(self, mock_env, mock_super):
        mock_super.return_value = Template()
        mock_env.kms_key_id = 'fake-key-id'
        x = MyConfigParser({}, 'my-stack').base_template()
        compare(x.mappings['KMS'], {'salt': {'key': 'fake-key-id'}})

    # http://mock.readthedocs.org/en/latest/patch.html#where-to-patch
    @patch('bootstrap_salt.config.ConfigParser.get_ec2_userdata')
    @patch.object(bootstrap_salt.config, 'env')
    def test_get_ec2_userdata(self, mock_env, mock_super):
        mock_super.return_value = []
        mock_env.kms_data_key = 'fake-key-data'
        version = pkg_resources.get_distribution("bootstrap_salt").version

        expected = [{'content': 'runcmd: [/tmp/bootstrap.sh v{0}]\n'.format(version),
                     'mime_type': 'text/cloud-config'},
                    {'content': "write_files:\n- {content: fake-key-data, encoding: b64, owner: 'root:root', path: /etc/salt.key.enc,\n  permissions: '0600'}\n- {content: '#!/bin/bash\n\n    REVISION=$1\n\n    wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/6080a18e6c7c2d49335978fa69fa63645b45bc2a/bootstrap-salt.sh\n    -O /tmp/bootstrap-salt.sh\n\n    chmod 700 /tmp/bootstrap-salt.sh\n\n    apt-get update && apt-get -y install python-pip git python-dev\n\n    pip install boto\n\n    pip install gnupg\n\n    cd /tmp\n\n    git clone --depth 1 --branch $REVISION https://github.com/ministryofjustice/bootstrap-salt.git\n\n    cd ./bootstrap-salt\n\n    cp -Lrf ./contrib/* /\n\n    /tmp/bootstrap-salt.sh git v2014.7.5\n\n    salt-call saltutil.sync_all\n\n    /usr/local/bin/salt_utils.py -s highstate\n\n    touch /tmp/bootstrap_done\n\n    ', owner: 'root:root', path: /tmp/bootstrap.sh, permissions: '0700'}\n", 'mime_type': 'text/cloud-config'}]  # NOQA

        x = MyConfigParser({}, 'my-stack').get_ec2_userdata()
        compare(x, expected)

    def tearDown(self):
        pass
