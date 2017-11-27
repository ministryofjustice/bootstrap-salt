#!/usr/bin/env python

import sys
import boto.ec2
import boto.cloudformation
import boto.ec2.autoscale
from boto.exception import BotoServerError
import urllib2
import time
import random


def get_aws_metadata():
    metadata_ip = '169.254.169.254'
    try:
        instance_id = urllib2.urlopen(
            'http://{0}/latest/meta-data/instance-id'.format(metadata_ip)).read().strip()
        region = urllib2.urlopen(
            'http://{0}/latest/meta-data/placement/availability-zone'.format(metadata_ip)).read().strip()[:-1]
        return {'aws_instance_id': instance_id, 'aws_region': region}
    except Exception as err:
        sys.stderr.write('tags_to_grains ERROR: %s\n' % str(err))
        return {'custom_grain_error': True}


_tags_to_grains_stack_name = 'NOT_FETCHED_YET'


def get_stack_name():
    global _tags_to_grains_stack_name
    if _tags_to_grains_stack_name == 'NOT_FETCHED_YET':
        # If we have problems *getting* the tags at all then retry/let the error bubble up
        tags = get_ec2_data()
        try:
            _tags_to_grains_stack_name = tags['aws:cloudformation:stack-name']
        except KeyError:
            _tags_to_grains_stack_name = None
    return _tags_to_grains_stack_name


def get_cf_data(attempt=0):
    try:
        stack_name = get_stack_name()
        if stack_name is None:
            return {}

        md = get_aws_metadata()
        conn = boto.cloudformation.connect_to_region(md['aws_region'])
        stack_outputs = conn.describe_stacks(stack_name)[0].outputs
        out = {}
        [out.update({o.key: o.value}) for o in stack_outputs]
        return out
    except BotoServerError:
        if attempt > 5:
            return {'custom_grain_error': True}
        time.sleep(random.randint(1, 5))
        attempt = attempt + 1
        return get_cf_data(attempt)
    except Exception as err:
        sys.stderr.write('tags_to_grains ERROR: %s\n' % str(err))
        return {'custom_grain_error': True}


def get_ec2_data(attempt=0):
    """
    This retrieves ec2 data for the instance e.g
    Project: courtfinder
    Role: docker
    Apps: search,admin
    Env: dev

    To transform this data into salt grains run:
    ``salt '*' saltutil.sync_all``
    """

    try:
        md = get_aws_metadata()
        conn = boto.ec2.connect_to_region(md['aws_region'])
        instance = conn.get_all_instances(
            instance_ids=[md['aws_instance_id']])[0].instances[0]
        return instance.tags
    except BotoServerError:
        if attempt > 5:
            return {'custom_grain_error': True}
        time.sleep(random.randint(1, 5))
        attempt = attempt + 1
        return get_ec2_data(attempt)
    except Exception as err:
        sys.stderr.write('tags_to_grains ERROR: %s\n' % str(err))
        return {'custom_grain_error': True}


def get_asg_data(attempt=0):
    """
    This retrieves asg tag data for the instance.
    """

    md = get_aws_metadata()

    try:
        stack_name = get_stack_name()
        conn = boto.ec2.autoscale.connect_to_region(md['aws_region'])
        instance = conn.get_all_autoscaling_instances(instance_ids=[md['aws_instance_id']])

        if not instance:
            return {}

        if not instance[0].group_name:
            return {}

        group_name = instance[0].group_name
        tagged_groups = [grp for grp in conn.get_all_groups(max_records=100) if grp.tags is not None]
        for grp in tagged_groups:
            for tag in grp.tags:
                if tag.key == 'aws:cloudformation:stack-name':
                    if str(tag.value) == str(stack_name):
                        group = grp

        tags = {}
        for i in group.tags:
            tags[str(i.key)] = str(i.value)

        return tags
    except BotoServerError:
        if attempt > 5:
            return {'custom_grain_error': True}
        time.sleep(random.randint(1, 5))
        attempt = attempt + 1
        return get_asg_data(attempt)
    except Exception as err:
        sys.stderr.write('tags_to_grains ERROR: %s\n' % str(err))
        return {'custom_grain_error': True}


if __name__ == '__main__':
    print get_ec2_data()
    print get_cf_data()
    print get_aws_metadata()
    print get_asg_data()
