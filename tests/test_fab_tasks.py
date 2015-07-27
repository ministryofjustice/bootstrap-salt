import unittest

from mock import patch

from testfixtures import compare

from fabric.api import env

from bootstrap_salt import fab_tasks


class TestFabTasks(unittest.TestCase):

    def setUp(self):
        pass

    def test_get_ips_batch(self):
        # Test one batch
        mock_ret = ['1.1.1.1', '2.2.2.2']
        with patch.object(fab_tasks, 'get_instance_ips', return_value=mock_ret):
            expected = [['{0}@1.1.1.1'.format(env.user), '{0}@2.2.2.2'.format(env.user)]]
            x = fab_tasks.get_ips_batch()
            compare(x, expected)
        # Test 50% batch
        mock_ret = ['1.1.1.1', '2.2.2.2', '3.3.3.3', '4.4.4.4']
        with patch.object(fab_tasks, 'get_instance_ips', return_value=mock_ret):
            expected = [['{0}@1.1.1.1'.format(env.user), '{0}@2.2.2.2'.format(env.user)],
                        ['{0}@3.3.3.3'.format(env.user), '{0}@4.4.4.4'.format(env.user)]]
            x = fab_tasks.get_ips_batch(0.5)
            compare(x, expected)
        # 50% batch uneven nodes
        mock_ret = ['1.1.1.1', '2.2.2.2', '3.3.3.3']
        with patch.object(fab_tasks, 'get_instance_ips', return_value=mock_ret):
            expected = [['{0}@1.1.1.1'.format(env.user), '{0}@2.2.2.2'.format(env.user)],
                        ['{0}@3.3.3.3'.format(env.user)]]
            x = fab_tasks.get_ips_batch(0.5)
            compare(x, expected)

    def tearDown(self):
        pass
