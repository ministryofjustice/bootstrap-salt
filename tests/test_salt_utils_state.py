import unittest
from mock import MagicMock, patch
from nose.tools import raises
from bootstrap_salt.salt_utils_state import SaltUtilsStateWrapper, SaltParserError, SaltStateError


class SaltUtilsStateTestCase(unittest.TestCase):

    def setUp(self):
        pass

    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_state_result_good(self,
                               mock_salt_output,
                               mock_salt_config,
                               mock_salt_client_caller):
        """
        test_state_result_good: Test calling a state and getting back a correct result
        """
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = ['This call succeeded']

        # Make actual call
        salt_utils_state = SaltUtilsStateWrapper()
        actual_result = salt_utils_state.state('12345')

        self.assertTrue(actual_result)

    @raises(SaltStateError)
    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_state_result_bad(self,
                              mock_salt_output,
                              mock_salt_config,
                              mock_salt_client_caller):
        """
        test_state_result_bad: Test calling a state and getting back a failed result
        """
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = ['This call failed']

        # Make actual call
        salt_utils_state = SaltUtilsStateWrapper()
        salt_utils_state.state('12345')

    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_state_result_with_dictionary_good(self,
                                               mock_salt_output,
                                               mock_salt_config,
                                               mock_salt_client_caller):
        """
        test_state_result_with_dictionary_good: Test calling a state and getting back a correct result as a dictionary
        """
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = {'state': {'result': True}}

        # Make actual call
        salt_utils_state = SaltUtilsStateWrapper()
        actual_result = salt_utils_state.state('12345')
        self.assertTrue(actual_result)

    @raises(SaltStateError)
    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_state_result_with_dictionary_bad(self,
                                              mock_salt_output,
                                              mock_salt_config,
                                              mock_salt_client_caller):
        """
        test_state_result_with_dictionary_bad: Test calling a state and getting back a failed result as a dictionary
        """
        # Construct nested caller function
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = {'state': {'result': False}}

        # Make actual call
        salt_utils_state = SaltUtilsStateWrapper()
        salt_utils_state.state('12345')

    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_highstate_result_good(self,
                                   mock_salt_output,
                                   mock_salt_config,
                                   mock_salt_client_caller):
        """
        test_highstate_result_good: Test calling a highstate and getting back a correct result
        """
        # Construct nested caller function
        instance = mock_salt_client_caller.return_value
        instance.function.return_value = ['This call succeeded']
        # Make actual call
        salt_utils_state = SaltUtilsStateWrapper()
        actual_result = salt_utils_state.state('highstate')
        self.assertTrue(actual_result)

    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_check_state_result_good(self,
                                     mock_salt_output,
                                     mock_salt_config,
                                     mock_salt_client_caller):
        """
        test_check_state_result_good: Test checking good state result
        """
        result = {'state': {'result': True},
                  'state1': {'result': True}}
        salt_utils_state = SaltUtilsStateWrapper()
        result = salt_utils_state.check_state_result(result)
        self.assertTrue(result)

    @raises(SaltStateError)
    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_check_state_result_dictionary_bad(self,
                                               mock_salt_output,
                                               mock_salt_config,
                                               mock_salt_client_caller):
        """
        test_check_state_result_dictionary_bad: Test checking failed state result as dictionary
        """
        result = {'state': {'result': False},
                  'state1': {'result': True}}
        salt_utils_state = SaltUtilsStateWrapper()
        salt_utils_state.check_state_result(result)

    @raises(SaltStateError)
    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_check_state_result_list_bad(self,
                                         mock_salt_output,
                                         mock_salt_config,
                                         mock_salt_client_caller):
        """
        test_check_state_result_list_bad: Test bad result as list
        """
        result = ['SOME SALT ERROR']
        salt_utils_state = SaltUtilsStateWrapper()
        salt_utils_state.check_state_result(result)

    @raises(SaltParserError)
    @patch('salt.client.Caller')
    @patch('salt.config')
    @patch('salt.output')
    def test_check_state_result_parse_error(self,
                                            mock_salt_output,
                                            mock_salt_config,
                                            mock_salt_client_caller):
        """
        test_check_state_result_parse_error: Test badly formatted result
        """
        result = 'SOME UNEXPECTED OUTPUT FORMAT'
        salt_utils_state = SaltUtilsStateWrapper()
        salt_utils_state.check_state_result(result)

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
