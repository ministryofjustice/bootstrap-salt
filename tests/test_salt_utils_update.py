import unittest
import mock
import sys

# This is a hack so that we don't need salt to run our tests
sys.modules['salt'] = mock.Mock()
sys.modules['salt.runner'] = mock.Mock()
sys.modules['salt.config'] = mock.Mock()
sys.modules['salt.output'] = mock.Mock()
sys.modules['salt.client'] = mock.Mock()
sys.modules['salt.utils'] = mock.Mock()
sys.modules['salt.log'] = mock.Mock()
sys.modules['salt.log.setup'] = mock.Mock()

import salt
from bootstrap_salt.salt_utils_update import SaltUtilsUpdateWrapper


class SaltUtilUpdateTestCase(unittest.TestCase):

    def setUp(self):
        self.salt_utils_update = SaltUtilsUpdateWrapper()
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
        self.salt_utils_update.get_salt_data = mock.Mock()
        x = False
        self.assertTrue(x)

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
