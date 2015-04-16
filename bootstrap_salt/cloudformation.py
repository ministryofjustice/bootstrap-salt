import boto.cloudformation
import boto.ec2
from boto.ec2 import autoscale
import utils


class Cloudformation(object):

    conn_cfn = None
    aws_region_name = None
    aws_profile_name = None

    def __init__(self, aws_profile_name, aws_region_name='eu-west-1'):
        self.aws_profile_name = aws_profile_name
        self.aws_region_name = aws_region_name
        self.conn_cfn = utils.connect_to_aws(boto.cloudformation, self)

    def get_stack_instances(self, stack_name_or_id):
        # get the stack
        stack = self.conn_cfn.describe_stacks(stack_name_or_id)
        print "Stack:", stack
        if not stack:
            print 'Empty stack'
            return []
        fn = lambda x: x.resource_type == 'AWS::AutoScaling::AutoScalingGroup'
        # get the scaling group
        scaling_group = filter(fn, stack[0].list_resources())
        if not scaling_group:
            print 'No scaling group found'
            return []
        scaling_group_id = scaling_group[0].physical_resource_id

        asc = utils.connect_to_aws(autoscale, self)

        # get the instance IDs for all instances in the scaling group
        instances = asc.get_all_groups(names=[scaling_group_id])[0].instances
        return instances

    def get_stack_instance_ids(self, stack_name_or_id):
        return [
            x.instance_id for x in self.get_stack_instances(stack_name_or_id)]
