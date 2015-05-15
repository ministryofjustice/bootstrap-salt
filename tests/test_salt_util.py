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

    def test_get_minions_batch(self):
        mock_result = mock.Mock()
        # No batch
        mock_config = {'cmd.return_value': {'minion1': 'blah',
                                            'minion2': 'blah'}}
        mock_result.configure_mock(**mock_config)
        mock_client = mock.Mock()
        mock_client.return_value = mock_result
        mock_c = mock.Mock(LocalClient=mock_client)
        salt.client = mock_c
        x = salt_utils.get_minions_batch('*')
        expected = [['minion1', 'minion2']]
        self.assertEqual(x, expected)

        # 50% batch
        mock_config = {'cmd.return_value': {'minion1': 'blah',
                                            'minion2': 'blah',
                                            'minion3': 'blah',
                                            'minion4': 'blah'}}
        mock_result.configure_mock(**mock_config)
        mock_client = mock.Mock()
        mock_client.return_value = mock_result
        mock_c = mock.Mock(LocalClient=mock_client)
        salt.client = mock_c

        x = salt_utils.get_minions_batch('*', 0.5)
        expected = [['minion4', 'minion1'], ['minion3', 'minion2']]
        self.assertEqual(x, expected)

        # 50% batch uneven minons
        mock_config = {'cmd.return_value': {'minion1': 'blah',
                                            'minion2': 'blah',
                                            'minion3': 'blah'}}
        mock_result.configure_mock(**mock_config)
        mock_client = mock.Mock()
        mock_client.return_value = mock_result
        mock_c = mock.Mock(LocalClient=mock_client)
        salt.client = mock_c

        x = salt_utils.get_minions_batch('*', 0.5)
        expected = [['minion1', 'minion3'], ['minion2']]
        self.assertEqual(x, expected)

    def test_state_result(self):
        salt.config = mock.Mock()
        mock_result = mock.Mock()
        mock_config = {'cmd.return_value': {'minon1': {'state': {'result': True}}}}
        mock_result.configure_mock(**mock_config)

        mock_client = mock.Mock()
        mock_client.return_value = mock_result

        mock_runner = mock.Mock(RunnerClient=mock_client)

        salt.runner = mock_runner
        x = salt_utils.state_result('12345')
        self.assertTrue(x)

    def test_no_state_result(self):
        salt.config = mock.Mock()
        mock_result = mock.Mock()
        mock_config = {'cmd.return_value': {}}
        mock_result.configure_mock(**mock_config)

        mock_client = mock.Mock()
        mock_client.return_value = mock_result

        mock_runner = mock.Mock(RunnerClient=mock_client)

        salt.runner = mock_runner
        x = salt_utils.state_result('12345')
        self.assertFalse(x)

    def test_check_state_result_good(self):
        result = {'minon1': {'state': {'result': True}},
                  'minion2': {'state': {'result': True}}}
        x = salt_utils.check_state_result(result)
        self.assertTrue(x)

    def test_check_state_result_bad(self):
        result = {'minon1': {'state': {'result': False}},
                  'minion2': {'state': {'result': True}}}
        with self.assertRaises(salt_utils.SaltStateError):
            salt_utils.check_state_result(result)

    def test_check_state_result_parse_error(self):
        result = {'minon1': ['SOME SALT PARSER ERROR']}
        with self.assertRaises(salt_utils.SaltParserError):
            salt_utils.check_state_result(result)

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
