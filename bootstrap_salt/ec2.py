import boto.ec2
import cloudformation
import ssh
import utils


class EC2:

    conn_cfn = None
    aws_region_name = None
    aws_profile_name = None

    def __init__(self, aws_profile_name, aws_region_name='eu-west-1'):
        self.aws_profile_name = aws_profile_name
        self.aws_region_name = aws_region_name

        self.conn_ec2 = utils.connect_to_aws(boto.ec2, self)

        self.cfn = cloudformation.Cloudformation(
            aws_profile_name=aws_profile_name,
            aws_region_name=aws_region_name
        )

    def get_instance_public_ips(self, instance_id_list):
        if not instance_id_list:
            return []
        return [x.ip_address for x in
                self.conn_ec2.get_only_instances(instance_ids=instance_id_list)]

    def get_instance_private_ips(self, instance_id_list):
        if not instance_id_list:
            return []
        return [x.private_ip_address for x in
                self.conn_ec2.get_only_instances(instance_ids=instance_id_list)]

    def set_instance_tags(self, instance_ids, tags=None):
        tags = tags if tags else {}
        return self.conn_ec2.create_tags(instance_ids, tags)

    def create_sg(self, name):
        return self.conn_ec2.create_security_group(
            name, 'bootstrap generated SG')

    def get_sg(self, name):
        groups = self.conn_ec2.get_all_security_groups(groupnames=[name])
        return groups[0] if groups else None

    def add_minion_to_sg(self, sg_obj, ip):
        return sg_obj.authorize(
            ip_protocol='tcp', from_port=4505,
            to_port=4506, cidr_ip='{0}/32'.format(ip))

    def get_instance_by_id(self, inst_id):
        resv = self.conn_ec2.get_all_reservations([inst_id])
        return [i for r in resv for i in r.instances][0] if resv else None

    def get_master_instance(self, stack_name_or_id):
        instances = self.cfn.get_stack_instances(
            stack_name_or_id,
            filters={'tag-key': 'SaltMaster'})
        return instances[0] if len(instances) else None

    def get_unconfigured_minions(self, stack_name_or_id, master_ip):
        """
        Get a list of all instances that need salt_master configuring.

        We define configuring as:

        - They haven't had salt installed (which would be the case when there
          is no 'SaltMasterPrvIP' tag
        - They are speaking to the wrong master (which would be if the salt
          master had to be re-built)

        """
        instances = self.cfn.get_stack_instances(stack_name_or_id)
        unconfigured = []
        for i in instances:
            if i.tags.get('SaltMasterPrvIP', '') == master_ip or i.tags.get('SaltMaster', ''):
                continue

            unconfigured.append(i)
        return unconfigured

    def is_ssh_up_on_all_instances(self, stack_id):
        """
        Returns False if no instances found
        Returns False if any instance is not available over SSH
        Returns True if all found instances available over SSH
        """
        instances = self.get_instance_public_ips(
            self.cfn.get_stack_instance_ids(stack_id))
        if not instances:
            return False
        if all([ssh.is_ssh_up(i) for i in instances]):
            return True
        return False

    def wait_for_ssh(self, stack_id, timeout=300, interval=30):
        return utils.timeout(timeout, interval)(
            self.is_ssh_up_on_all_instances)(stack_id)
