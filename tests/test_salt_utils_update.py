import unittest
from mock import call, MagicMock, patch
from bootstrap_salt.salt_utils_update import SaltUtilsUpdateWrapper


class SaltUtilsUpdateTestCase(unittest.TestCase):

    def setUp(self):
        pass

    @patch('salt.client.Caller')
    @patch('bootstrap_salt.salt_utils_update.SaltUtilsUpdateWrapper.get_salt_data')
    def test_sync_remote_salt_data(self,
                                   mock_get_salt_data,
                                   mock_salt_client_caller):
        """
        test_sync_remote_salt_data: syncing data call makes the expected calls
        """
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = MagicMock()
        instance.function.return_value.side_effect = [
            'cache_clear dict',
            'sync data dict'
        ]
        # Make actual call
        salt_utils_update = SaltUtilsUpdateWrapper()
        salt_utils_update.sync_remote_salt_data()
        mock_get_salt_data.assert_called_once()

        expected_method_calls = [
            call.function('saltutil.clear_cache'),
            call.function('saltutil.sync_all', 'refresh=True')
        ]
        self.assertEqual(instance.method_calls,
                         expected_method_calls,
                         "test_sync_remote_salt_data: salt caller function "
                         "was not called with all the expected methods")

    @patch('salt.client.Caller')
    @patch('bootstrap_salt.salt_utils_update.SaltUtilsUpdateWrapper.get_salt_data')
    def test_sync_remote_salt_data_no_clear_cache(self,
                                                  mock_get_salt_data,
                                                  mock_salt_client_caller):
        """
        test_sync_remote_salt_data_no_clear_cache: syncing data call makes the expected calls without clearing cache
        """
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = MagicMock()
        instance.function.return_value.side_effect = [
            'cache_clear dict',
            'sync data dict'
        ]
        # Make actual call
        salt_utils_update = SaltUtilsUpdateWrapper()
        salt_utils_update.sync_remote_salt_data(clear_cache=False)
        mock_get_salt_data.assert_called_once()

        expected_method_calls = [
            call.function('saltutil.sync_all', 'refresh=True')
        ]
        self.assertEqual(instance.method_calls,
                         expected_method_calls,
                         "test_sync_remote_salt_data: salt caller function "
                         "was not called with all the expected methods. "
                         "\nactual: {} \nexpected: {}"
                         .format(instance.method_calls,
                                 expected_method_calls)
                         )

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
