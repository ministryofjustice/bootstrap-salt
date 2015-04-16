#!/usr/bin/env python

import os
from StringIO import StringIO
import sys
import random
import yaml

from fabric.api import env, task, sudo, put
from fabric.contrib.project import upload_project

# from bootstrap_salt.config import ProjectConfig, ConfigParser
from cloudformation import Cloudformation
from ec2 import EC2

# GLOBAL VARIABLES
env.aws = None
TIMEOUT = 3600
RETRY_INTERVAL = 10

# This is needed because pkgutil wont pick up modules
# imported in a fabfile.
path = env.real_fabfile or os.getcwd()
sys.path.append(os.path.dirname(path))


@task
def aws(x):
    env.aws = str(x).lower()


def get_stack_name():
    if hasattr(env, 'stack_name'):
        return env.stack_name
    return "%s-%s" % (env.application, env.environment)


def _validate_fabric_env():
    if env.aws is None:
        print "\n[ERROR] Please specify an AWS account, e.g 'aws:dev'"
        sys.exit(1)

    if not hasattr(env, 'aws_region'):
        env.aws_region = 'eu-west-1'


def get_connection(klass):
    _validate_fabric_env()
    return klass(env.aws, env.aws_region)


@task
def find_master():
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    master = ec2.get_master_instance(stack_name).ip_address
    print 'Salt master public address: {0}'.format(master)
    return master

@task
def setup_salt(stack_id):
    if stack_id is None:
        print "\n[ERROR] Please specify a stack_id, e.g 'setup_salt:<stack_id>'"
        sys.exit(1)
    # cfn = Cloudformation(env.aws)
    # print cfn
    # print cfn.get_stack_instances(stack_id)
    install_master(stack_id)


# def get_candidate_minions():
#     stack_name = get_stack_name()
#     cfn = get_connection(Cloudformation)
#     ec2 = get_connection(EC2)
#     instance_ids = cfn.get_stack_instance_ids(stack_name)
#     stack_name = get_stack_name()
#     master_instance_id = ec2.get_master_instance(stack_name).id
#     instance_ids.remove(master_instance_id)
#     return instance_ids
#
#
# @task
# def install_minions():
#     stack_name = get_stack_name()
#     ec2 = get_connection(EC2)
#     print "Waiting for SSH on all instances..."
#     ec2.wait_for_ssh(stack_name)
#     candidates = get_candidate_minions()
#     existing_minions = ec2.get_minions(stack_name)
#     to_install = list(set(candidates).difference(set(existing_minions)))
#     if not to_install:
#         return
#     public_ips = ec2.get_instance_public_ips(to_install)
#     sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
#     stack_name = get_stack_name()
#     master_inst = ec2.get_master_instance(stack_name)
#     master_public_ip = master_inst.ip_address
#     master_prv_ip = master_inst.private_ip_address
#     ec2.set_instance_tags(to_install, {'SaltMasterPrvIP': master_prv_ip})
#     for inst_ip in public_ips:
#         env.host_string = 'ubuntu@%s' % inst_ip
#         sudo('wget https://raw.githubusercontent.com/ministryofjustice/bootstrap-cfn/master/scripts/bootstrap-salt.sh -O /tmp/moj-bootstrap.sh')
#         sudo('chmod 755 /tmp/moj-bootstrap.sh')
#         sudo('/tmp/moj-bootstrap.sh')
#         sudo(
#             'wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' %
#             sha)
#         sudo('chmod 755 /tmp/bootstrap-salt.sh')
#         sudo(
#             '/tmp/bootstrap-salt.sh -A `cat /etc/tags/SaltMasterPrvIP` git v2014.1.4')
#         env.host_string = 'ubuntu@%s' % master_public_ip
#         sudo('salt-key -y -A')
#
#
@task
def install_master(stack_id):
    #stack_name = get_stack_name()
    stack_name = stack_id
    ec2 = get_connection(EC2)
    cfn = get_connection(Cloudformation)
    print "Waiting for SSH on all instances..."
    ec2.wait_for_ssh(stack_name)
    instance_ids = cfn.get_stack_instance_ids(stack_name)
    master_inst = ec2.get_master_instance(stack_name)
    master = master_inst.id if master_inst else random.choice(instance_ids)
    master_prv_ip = ec2.get_instance_private_ips([master])[0]
    master_public_ip = ec2.get_instance_public_ips([master])[0]
    ec2.set_instance_tags(instance_ids, {'SaltMasterPrvIP': master_prv_ip})
    ec2.set_instance_tags(master, {'SaltMaster': 'True'})

    stack_ips = ec2.get_instance_private_ips(instance_ids)
    stack_ips.remove(master_prv_ip)
    stack_public_ips = ec2.get_instance_public_ips(instance_ids)
    stack_public_ips.remove(master_public_ip)
    env.host_string = 'ubuntu@%s' % master_public_ip
    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    sudo('wget https://raw.githubusercontent.com/ministryofjustice/bootstrap-cfn/master/scripts/bootstrap-salt.sh -O /tmp/moj-bootstrap.sh')
    sudo('chmod 755 /tmp/moj-bootstrap.sh')
    sudo('/tmp/moj-bootstrap.sh')
    sudo(
        'wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' %
        sha)
    sudo('chmod 755 /tmp/bootstrap-salt.sh')
    sudo(
        '/tmp/bootstrap-salt.sh -M -A `cat /etc/tags/SaltMasterPrvIP` git v2014.1.4')
    sudo('salt-key -y -A')
#
# @task
# def rsync():
#
#     _validate_fabric_env()
#
#     work_dir = os.path.dirname(env.real_fabfile)
#
#     project_config = ProjectConfig(env.config, env.environment, env.stack_passwords)
#     stack_name = get_stack_name()
#     cfg = project_config.config
#     salt_cfg = cfg.get('salt', {})
#
#     local_salt_dir = os.path.join(
#         work_dir,
#         salt_cfg.get('local_salt_dir', 'salt'),
#         '.')
#     local_pillar_dir = os.path.join(
#         work_dir,
#         salt_cfg.get('local_pillar_dir', 'pillar'),
#         '.')
#     local_vendor_dir = os.path.join(
#         work_dir,
#         salt_cfg.get('local_vendor_dir', 'vendor'),
#         '.')
#
#     remote_state_dir = salt_cfg.get('remote_state_dir', '/srv/salt')
#     remote_pillar_dir = salt_cfg.get('remote_pillar_dir', '/srv/pillar')
#
#     master_ip = find_master()
#     env.host_string = '{0}@{1}'.format(env.user, master_ip)
#     sudo('mkdir -p {0}'.format(remote_state_dir))
#     sudo('mkdir -p {0}'.format(remote_pillar_dir))
#     upload_project(
#         remote_dir=remote_state_dir,
#         local_dir=os.path.join(local_vendor_dir, '_root', '.'),
#         use_sudo=True)
#     upload_project(
#         remote_dir='/srv/',
#         local_dir=os.path.join(local_vendor_dir, 'formula-repos'),
#         use_sudo=True)
#     upload_project(
#         remote_dir=remote_state_dir,
#         local_dir=local_salt_dir,
#         use_sudo=True)
#     upload_project(
#         remote_dir=remote_pillar_dir,
#         local_dir=os.path.join(local_pillar_dir, env.environment, '.'),
#         use_sudo=True)
#     cf_sls = StringIO(yaml.dump(cfg))
#     put(
#         remote_path=os.path.join(
#             remote_pillar_dir,
#             'cloudformation.sls'),
#         local_path=cf_sls,
#         use_sudo=True)
