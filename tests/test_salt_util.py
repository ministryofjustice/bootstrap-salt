import unittest
import mock
import sys
# This is a hack so that we don't need salt to run our tests
sys.modules['salt'] = mock.Mock()
sys.modules['salt.runner'] = mock.Mock()
sys.modules['salt.config'] = mock.Mock()
sys.modules['salt.output'] = mock.Mock()
sys.modules['salt.client'] = mock.Mock()
import salt
from bootstrap_salt import salt_utils


class SaltUtilTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def test_state_result(self):
        salt.config = mock.Mock()
        mock_result = mock.Mock()
        mock_config = {'function.return_value': {'state': {'result': True}}}
        mock_result.configure_mock(**mock_config)

        mock_client = mock.Mock()
        mock_client.return_value = mock_result

        mock_caller = mock.Mock(Caller=mock_client)

        salt.client = mock_caller
        x = salt_utils.state('12345')
        self.assertTrue(x)

    def test_check_state_result_good(self):
        result = {'state': {'result': True},
                  'state1': {'result': True}}
        x = salt_utils.check_state_result(result)
        self.assertTrue(x)

    def test_check_state_result_bad(self):
        result = {'state': {'result': False},
                  'state1': {'result': True}}
        with self.assertRaises(salt_utils.SaltStateError):
            salt_utils.check_state_result(result)

    def test_check_state_result_parse_error(self):
        result = ['SOME SALT PARSER ERROR']
        with self.assertRaises(salt_utils.SaltParserError):
            salt_utils.check_state_result(result)

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
