import base64
import unittest

from bootstrap_salt.kms import KMS

import boto.kms

import mock

from mock import patch

from testfixtures import compare


class TestKMS(unittest.TestCase):

    def setUp(self):
        self.env = mock.Mock()
        self.env.aws = 'dev'
        self.env.aws_profile = 'the-profile-name'
        kms_mock = mock.Mock()
        kms_connect_result = mock.Mock(name='cf_connect')
        kms_mock.return_value = kms_connect_result
        boto.kms.connect_to_region = kms_mock
        self.k = KMS(self.env.aws_profile)

    def test_get_key_id(self):
        mock_ret = {'Aliases': [{'TargetKeyId': 'mock-key-id',
                                 'AliasName': 'alias/mock-alias'}]}
        with patch.object(self.k.conn_kms, 'list_aliases', return_value=mock_ret):
            ret = self.k.get_key_id('mock-alias')
            compare(ret, 'mock-key-id')

    def test_create_key(self):
        mock_ret = {'KeyMetadata': {'KeyId': 'mock-key-id'}}
        with patch.object(self.k.conn_kms, 'create_key', return_value=mock_ret):
            ret = self.k.create_key('mock-alias')
            self.k.conn_kms.create_alias.assert_called_with('alias/mock-alias', 'mock-key-id')
            compare(ret, 'mock-key-id')

    def test_generate_data_key(self):
        mock_ret = {'CiphertextBlob': 'encryptedblob'}
        expect = base64.b64encode('encryptedblob')
        with patch.object(self.k.conn_kms,
                          'generate_data_key',
                          return_value=mock_ret):
            ret = self.k.generate_data_key('mock-key-id')
            compare(ret, expect)

    def test_decrypt(self):
        with patch.object(self.k.conn_kms, 'decrypt', return_value='mock-ret'):
            ret = self.k.decrypt('cipherblob')
            compare(ret, 'mock-ret')

    def tearDown(self):
        pass
