import unittest

from mock import patch

from testfixtures import compare

from bootstrap_salt import fab_tasks


class TestFabTasks(unittest.TestCase):

    def setUp(self):
        pass

    def test_get_ips_batch(self):
        # Test one batch
        mock_ret = ['1.1.1.1', '2.2.2.2']
        with patch.object(fab_tasks, 'get_instance_ips', return_value=mock_ret):
            expected = [['1.1.1.1', '2.2.2.2']]
            x = fab_tasks.get_ips_batch()
            compare(x, expected)
        # Test 50% batch
        mock_ret = ['1.1.1.1', '2.2.2.2', '3.3.3.3', '4.4.4.4']
        with patch.object(fab_tasks, 'get_instance_ips', return_value=mock_ret):
            expected = [['1.1.1.1', '2.2.2.2'],
                        ['3.3.3.3', '4.4.4.4']]
            x = fab_tasks.get_ips_batch(0.5)
            compare(x, expected)
        # 50% batch uneven nodes
        mock_ret = ['1.1.1.1', '2.2.2.2', '3.3.3.3']
        with patch.object(fab_tasks, 'get_instance_ips', return_value=mock_ret):
            expected = [['1.1.1.1', '2.2.2.2'],
                        ['3.3.3.3']]
            x = fab_tasks.get_ips_batch(0.5)
            compare(x, expected)

    def tearDown(self):
        pass

    @patch('bootstrap_salt.fab_tasks.bcfn_delete')
    def test_cfn_delete_wrapper(self, mock_cfn_delete):
        fab_tasks.cfn_delete()
        mock_cfn_delete.assert_called_once_with(pre_delete_callbacks=[fab_tasks.delete_tar])

    @patch('bootstrap_salt.fab_tasks.bcfn_delete')
    def test_cfn_delete_wrapper_with_task(self, mock_cfn_delete):
        x = lambda x: x
        fab_tasks.cfn_delete(pre_delete_callbacks=[x])
        mock_cfn_delete.assert_called_once_with(pre_delete_callbacks=[x, fab_tasks.delete_tar])
