import tempfile
import unittest
import mock
import yaml
import boto.cloudformation
import boto.ec2.autoscale
import paramiko
from bootstrap_salt import cloudformation
from bootstrap_salt import ec2
from bootstrap_salt import ssh
from paramiko.ssh_exception import AuthenticationException
import socket
import os


class BootstrapSaltTestCase(unittest.TestCase):

    def setUp(self):
        self.work_dir = tempfile.mkdtemp()

        self.env = mock.Mock()
        self.env.aws = 'dev'
        self.env.aws_profile = 'the-profile-name'
        self.env.environment = 'dev'
        self.env.application = 'unittest-app'
        self.env.config = os.path.join(self.work_dir, 'test_config.yaml')

        config = {'dev': {'ec2': {'auto_scaling': {'desired': 1, 'max': 3,
                                                   'min': 0},
                                  'block_devices': [{'DeviceName': '/dev/sda1',
                                                     'VolumeSize': 10},
                                                    {'DeviceName': '/dev/sdf',
                                                     'VolumeSize': 10}],
                                  'parameters': {'InstanceType': 't2.micro',
                                                 'KeyName': 'default'},
                                  'security_groups': [{'CidrIp': '0.0.0.0/0',
                                                       'FromPort': 22,
                                                       'IpProtocol': 'tcp',
                                                       'ToPort': 22},
                                                      {'CidrIp': '0.0.0.0/0',
                                                       'FromPort': 80,
                                                       'IpProtocol': 'tcp',
                                                       'ToPort': 80}],
                                  'tags': {'Apps': 'test', 'Env': 'dev',
                                           'Role': 'docker'}},
                          'elb': [{'hosted_zone': 'kyrtest.pf.dsd.io.',
                                   'listeners': [{'InstancePort': 80,
                                                  'LoadBalancerPort': 80,
                                                  'Protocol': 'TCP'},
                                                 {'InstancePort': 443,
                                                  'LoadBalancerPort': 443,
                                                  'Protocol': 'TCP'}],
                                   'name': 'test-dev-external',
                                   'scheme': 'internet-facing'},
                                  {'hosted_zone': 'kyrtest.pf.dsd.io.',
                                   'listeners': [{'InstancePort': 80,
                                                  'LoadBalancerPort': 80,
                                                  'Protocol': 'TCP'}],
                                   'name': 'test-dev-internal',
                                   'scheme': 'internet-facing'}],
                          'rds': {'backup-retention-period': 1,
                                  'db-engine': 'postgres',
                                  'db-engine-version': '9.3.5',
                                  'db-master-password': 'testpassword',
                                  'db-master-username': 'testuser',
                                  'db-name': 'test',
                                  'identifier': 'test-dev',
                                  'instance-class': 'db.t2.micro',
                                  'multi-az': False,
                                  'storage': 5,
                                  'storage-type': 'gp2'},
                          'master_zone': 'blah.dsd.io',
                          's3': {'static-bucket-name': 'moj-test-dev-static'}}}
        yaml.dump(config, open(self.env.config, 'w'))

        self.stack_name = '{0}-{1}'.format(self.env.application,
                                           self.env.environment)
        self.real_is_ssh_up = ssh.is_ssh_up

        self.ec2_mock = mock.Mock(name="boto.ec2.connect_to_region")
        self.ec2_connect_result = mock.Mock(name='cf_connect')
        self.ec2_mock.return_value = self.ec2_connect_result
        boto.ec2.connect_to_region = self.ec2_mock

        cfn_mock = mock.Mock(name="boto.cloudformation.connect_to_region")
        self.cfn_conn_mock = mock.Mock(name='cf_connect')
        cfn_mock.return_value = self.cfn_conn_mock
        boto.cloudformation.connect_to_region = cfn_mock

    def test_get_stack_id(self):
        stack_id = "arn:aws:cloudformation:eu-west-1:123/stack-name/uuid"

        stack = mock.Mock()
        type(stack).stack_id = stack_id
        self.cfn_conn_mock.describe_stacks.return_value = [stack]

        cfn = cloudformation.Cloudformation(self.env.aws_profile, 'aws_region')
        self.assertEqual(cfn.get_stack_id("stack-name"), stack_id)
        self.assertEqual(cfn.get_stack_id(stack_id), stack_id)

    def test_filter_stack_instances_when_no_stack(self):
        stack_name = "our-stack"
        stack_id = "aws:arn:stack-id"
        cfn = cloudformation.Cloudformation(self.env.aws_profile, 'aws_region')

        cfn.get_stack_id = mock.Mock(return_value=stack_id)

        cfn.conn_ec2.get_all_reservations = mock.Mock(return_value=[])

        self.assertEqual(cfn.filter_stack_instances(stack_name, {}), [])

        self.assertEqual(
            cfn.conn_ec2.get_all_reservations.get_all_reservations.called,
            False,
            "get_all_reservations should not be called")

    def test_filter_stack_instances(self):
        """
        All we care about testing in this function is that we call
        boto.ec2.get_all_reservations with the correct filter tags - we trust
        boto has implemented that function correctly
        """
        stack_name = "our-stack"
        stack_id = "aws:arn:stack-id"
        cfn = cloudformation.Cloudformation(self.env.aws_profile, 'aws_region')

        cfn.get_stack_id = mock.Mock(return_value=stack_id)

        instance = mock.Mock(name="MockInstance")
        reservation = mock.Mock()
        type(reservation).instances = mock.PropertyMock(return_value=[instance])

        cfn.conn_ec2.get_all_reservations = mock.Mock(return_value=[reservation])

        got = cfn.filter_stack_instances(stack_name, {})
        expected = [instance]
        self.assertEqual(got, expected)

        # Check we called boto with the right filters
        cfn.conn_ec2.get_all_reservations.assert_called_once_with(filters={
            'tag:aws:cloudformation:stack-id': stack_id,
        })

        cfn.conn_ec2.get_all_reservations.reset_mock()
        cfn.conn_ec2.get_all_reservations.return_value = []
        self.assertEqual(cfn.filter_stack_instances(stack_name, {'tag:x': '1'}), [])
        cfn.conn_ec2.get_all_reservations.assert_called_once_with(filters={
            'tag:aws:cloudformation:stack-id': stack_id,
            'tag:x': '1',
        })

    def test_get_stack_instances(self):
        stack_name = "our-stack"
        cfn = cloudformation.Cloudformation(self.env.aws_profile, 'aws_region')

        cfn.filter_stack_instances = mock.Mock(return_value=[])
        cfn.get_stack_instances(stack_name)
        cfn.filter_stack_instances.assert_called_once_with(stack_name, filters={
            'instance-state-name': 'running'
        })

        cfn.filter_stack_instances.reset_mock()
        cfn.get_stack_instances(stack_name, running_only=False)
        cfn.filter_stack_instances.assert_called_once_with(stack_name, filters={})

    def test_get_stack_instance_ids(self):
        stack_name = "our-stack"
        cfn = cloudformation.Cloudformation(self.env.aws_profile, 'aws_region')

        cfn.get_stack_instances = mock.Mock(return_value=[])
        cfn.get_stack_instance_ids(stack_name)
        cfn.get_stack_instances.assert_called_once_with(stack_name, running_only=True)

    def test_get_instance_public_ips_list_empty(self):

        mock_config = {'get_only_instances.return_value': []}
        self.ec2_connect_result.configure_mock(**mock_config)

        x = ec2.EC2(self.env.aws_profile).get_instance_public_ips([])
        self.assertEqual(x, [])

    def get_get_instance_public_ips_list(self):
        instance_mock = mock.Mock()
        ip_address = mock.PropertyMock(return_value='1.1.1.1')
        type(instance_mock).ip_address = ip_address

        ec2_mock = mock.Mock()
        ec2_connect_result = mock.Mock(name='cf_connect')
        ec2_mock.return_value = ec2_connect_result
        mock_config = {'get_only_instances.return_value': [instance_mock]}
        ec2_connect_result.configure_mock(**mock_config)
        boto.ec2.connect_to_region = ec2_mock

        ec = ec2.EC2(self.env.aws_profile)
        ips = ec.get_instance_public_ips(['i-12345'])
        self.assertEqual(ips, ['1.1.1.1'])

    def test_is_ssh_up_when_no_instances(self):
        '''
        This is to test that is_ssh_up_on_all_instances
        returns False when there are no instances running
        '''
        ec = ec2.EC2(self.env.aws_profile)

        ec.cfn.get_stack_instance_ids = mock.Mock(return_value=[])

        ssh_mock = mock.Mock()
        ssh_mock.side_effect = [True, True]
        ssh.is_ssh_up = ssh_mock

        self.assertFalse(ec.is_ssh_up_on_all_instances(self.stack_name))
        ssh.is_ssh_up.asset_has_calls([])

    def test_is_ssh_up_on_all_instances(self):
        ec = ec2.EC2(self.env.aws_profile)
        ec.get_instance_public_ips = mock.Mock(return_value=['1.2.3.4', '2.3.4.5'])
        ec.cfn.get_stack_instance_ids = mock.Mock(return_value=['i-1', 'i-2'])

        ssh_mock = mock.Mock()
        ssh_mock.side_effect = [True, True]
        ssh.is_ssh_up = ssh_mock

        self.assertTrue(ec.is_ssh_up_on_all_instances(self.stack_name))
        ssh_mock.assert_has_calls([mock.call('1.2.3.4'), mock.call('2.3.4.5')])

    def test_is_ssh_not_up_on_all_instances(self):
        ec = ec2.EC2(self.env.aws_profile)

        ec.get_instance_public_ips = mock.Mock(return_value=['1.2.3.4', '2.3.4.5'])
        ec.cfn.get_stack_instance_ids = mock.Mock(return_value=['i-1', 'i-2'])

        ssh_mock = mock.Mock()
        ssh_mock.side_effect = [True, False]
        ssh.is_ssh_up = ssh_mock

        self.assertFalse(ec.is_ssh_up_on_all_instances(self.stack_name))
        ssh_mock.assert_has_calls([mock.call('1.2.3.4'), mock.call('2.3.4.5')])

    def test_get_unconfigured_minions(self):
        ec = ec2.EC2(self.env.aws_profile)

        master_prv_ip = '10.0.0.1'

        master = mock.Mock(name="MockInstanceMaster")
        type(master).tags = mock.PropertyMock(return_value={'SaltMaster': 'True', 'SaltMasterPrvIP': master_prv_ip})

        # An unconfigured minion
        minion_1 = mock.Mock(name="MockInstance1")
        type(minion_1).tags = mock.PropertyMock(return_value={})

        # To the wrong master
        minion_2 = mock.Mock(name="MockInstance2")
        type(minion_2).tags = mock.PropertyMock(return_value={'SaltMasterPrvIP': '10.0.0.2'})

        # Correctly
        minion_3 = mock.Mock(name="MockInstance3")
        type(minion_3).tags = mock.PropertyMock(return_value={'SaltMasterPrvIP': master_prv_ip})

        ec.cfn.get_stack_instances = mock.Mock(return_value=[master, minion_1, minion_2, minion_3])

        got = ec.get_unconfigured_minions(self.stack_name, master_prv_ip)
        expected = [minion_1, minion_2]
        self.assertEqual(got, expected)

    def test_is_ssh_up(self):
        mock_p = mock.Mock()
        mock_client = mock.Mock()
        mock_config = {'connect.side_effect':AuthenticationException}
        mock_client.configure_mock(**mock_config)
        mock_p.return_value = mock_client 
        paramiko.SSHClient = mock_p
        self.assertTrue(ssh.is_ssh_up('1.1.1.1'))

    def test_is_ssh_not_up(self):
        mock_p = mock.Mock()
        mock_client = mock.Mock()
        mock_config = {'connect.side_effect':socket.error}
        mock_client.configure_mock(**mock_config)
        mock_p.return_value = mock_client 
        paramiko.SSHClient = mock_p
        self.assertFalse(ssh.is_ssh_up('1.1.1.1'))

    def tearDown(self):
        ssh.is_ssh_up = self.real_is_ssh_up

if __name__ == '__main__':
    unittest.main()
