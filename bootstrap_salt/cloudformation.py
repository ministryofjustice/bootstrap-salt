import boto.cloudformation
import boto.ec2
from boto.ec2 import autoscale
import utils


class Cloudformation(object):

    conn_cfn = None
    conn_ec2 = None
    aws_region_name = None
    aws_profile_name = None

    def __init__(self, aws_profile_name, aws_region_name='eu-west-1'):
        self.aws_profile_name = aws_profile_name
        self.aws_region_name = aws_region_name
        self.conn_cfn = utils.connect_to_aws(boto.cloudformation, self)
        self.conn_ec2 = utils.connect_to_aws(boto.ec2, self)

    def get_stack_id(self, stack_name_or_id):
        """
        Takes a stack name or id and converts it to the id
        """
        stack = self.conn_cfn.describe_stacks(stack_name_or_id)
        if len(stack) > 1:
            raise RuntimeError("get_stack_id expected 0 or 1 stacks, but got {0}".format(len(stack)))

        return stack[0].stack_id if len(stack) else None

    def filter_stack_instances(self, stack_name_or_id, filters):
        stack_id = self.get_stack_id(stack_name_or_id)

        if not stack_id:
            return []

        filters = filters.copy()
        filters['tag:aws:cloudformation:stack-id'] = stack_id

        resv = self.conn_ec2.get_all_reservations(filters=filters)
        return [i for r in resv for i in r.instances]

    def get_stack_instances(self, stack_name_or_id, running_only=True, filters={}):
        """
        Return boto Instance objects for every instance belonging to the stack
        """
        if running_only:
            filters['instance-state-name'] = 'running'

        return self.filter_stack_instances(stack_name_or_id, filters=filters)

    def get_stack_instance_ids(self, stack_name_or_id, running_only=True):
        return [
            x.id for x in self.get_stack_instances(stack_name_or_id, running_only=running_only)]
