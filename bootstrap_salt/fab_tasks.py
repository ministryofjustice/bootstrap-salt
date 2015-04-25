#!/usr/bin/env python

import os
from StringIO import StringIO
import sys
import yaml

from fabric.api import env, task, sudo, put
from fabric.contrib.project import upload_project
from cloudformation import Cloudformation
from ec2 import EC2
import bootstrap_cfn.config as cfn_config
from bootstrap_cfn.fab_tasks import _validate_fabric_env, get_stack_name

# GLOBAL VARIABLES
env.aws = None
TIMEOUT = 3600
RETRY_INTERVAL = 10

# This is needed because pkgutil wont pick up modules
# imported in a fabfile.
path = env.real_fabfile or os.getcwd()
sys.path.append(os.path.dirname(path))


env.stack = None


@task
def aws(x):
    env.aws = str(x).lower()


@task
def environment(x):
    env.environment = str(x).lower()


@task
def application(x):
    env.application = str(x).lower()


@task
def config(x):
    env.config = str(x).lower()


@task
def setup(stack_name=None):
    install_master()
    install_minions()


def get_connection(klass):
    _validate_fabric_env()
    return klass(env.aws, env.aws_region)


@task
def find_master():
    _validate_fabric_env()
    ec2 = get_connection(EC2)
    master_ip = ec2.get_master_instance().ip_address
    print 'Salt master public address: {0}'.format(master_ip)
    return master_ip


def get_candidate_minions(stack_name):
    cfn = get_connection(Cloudformation)
    ec2 = get_connection(EC2)
    instance_ids = cfn.get_stack_instance_ids(stack_name)
    master_instance_id = ec2.get_master_instance().id
    instance_ids.remove(master_instance_id)
    return instance_ids


def install_minions():
    _validate_fabric_env()
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    print "Waiting for SSH on all instances..."
    ec2.wait_for_ssh(stack_name)
    candidates = get_candidate_minions(stack_name)
    existing_minions = ec2.get_minions(stack_name)
    to_install = list(set(candidates).difference(set(existing_minions)))
    if not to_install:
        return
    public_ips = ec2.get_instance_public_ips(to_install)
    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    master_inst = ec2.get_master_instance()
    master_public_ip = master_inst.ip_address
    master_prv_ip = master_inst.private_ip_address
    ec2.set_instance_tags(to_install, {'SaltMasterPrvIP': master_prv_ip})
    for inst_ip in public_ips:
        env.host_string = 'ubuntu@%s' % inst_ip
        sudo('wget https://raw.githubusercontent.com/ministryofjustice/bootstrap-salt/master/scripts/bootstrap-salt.sh -O /tmp/moj-bootstrap.sh')
        sudo('chmod 755 /tmp/moj-bootstrap.sh')
        sudo('/tmp/moj-bootstrap.sh')
        sudo(
            'wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' %
            sha)
        sudo('chmod 755 /tmp/bootstrap-salt.sh')
        sudo(
            '/tmp/bootstrap-salt.sh -A `cat /etc/tags/SaltMasterPrvIP` git v2014.1.4')
        env.host_string = 'ubuntu@%s' % master_public_ip
        sudo('salt-key -y -A')


@task
def install_master():
    _validate_fabric_env()

    ec2 = get_connection(EC2)
    master = ec2.get_master_instance()

    print "Waiting for SSH on master..."
    ec2.wait_for_ssh([master.id])
    print "Ready"

    ec2.set_instance_tags(master.id, {'SaltMaster': 'True'})

    env.host_string = 'ubuntu@%s' % master.ip_address
    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    sudo('wget https://raw.githubusercontent.com/ministryofjustice/bootstrap-salt/master/scripts/bootstrap-salt.sh -O /tmp/moj-bootstrap.sh')
    sudo('chmod 755 /tmp/moj-bootstrap.sh')
    sudo('/tmp/moj-bootstrap.sh')
    sudo(
        'wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' %
        sha)
    sudo('chmod 755 /tmp/bootstrap-salt.sh')
    sudo(
        '/tmp/bootstrap-salt.sh -M -A `cat /etc/tags/SaltMasterPrvIP`\
         git v2014.1.4')
    sudo('salt-key -y -A')


@task
def set_master_private_ip():
    _validate_fabric_env()
    stack_name = get_stack_name()

    ec2 = get_connection(EC2)
    cfn = get_connection(Cloudformation)

    master = ec2.get_master_instance()
    instance_ids = cfn.get_stack_instance_ids(stack_name)

    ec2.set_instance_tags(instance_ids, {'SaltMasterPrvIP': master.ip_address})


@task
def rsync():
    _validate_fabric_env()
    work_dir = os.path.dirname(env.real_fabfile)
    project_config = cfn_config.ProjectConfig(env.config,
                                              env.environment,
                                              env.stack_passwords)
    cfg = project_config.config

    salt_cfg = cfg.get('salt', {})

    local_salt_dir = os.path.join(
        work_dir,
        salt_cfg.get('local_salt_dir', 'salt'),
        '.')
    local_pillar_dir = os.path.join(
        work_dir,
        salt_cfg.get('local_pillar_dir', 'pillar'),
        '.')
    local_vendor_dir = os.path.join(
        work_dir,
        salt_cfg.get('local_vendor_dir', 'vendor'),
        '.')

    remote_state_dir = salt_cfg.get('remote_state_dir', '/srv/salt')
    remote_pillar_dir = salt_cfg.get('remote_pillar_dir', '/srv/pillar')

    master_ip = find_master()
    env.host_string = '{0}@{1}'.format(env.user, master_ip)
    sudo('mkdir -p {0}'.format(remote_state_dir))
    sudo('mkdir -p {0}'.format(remote_pillar_dir))
    upload_project(
        remote_dir=remote_state_dir,
        local_dir=os.path.join(local_vendor_dir, '_root', '.'),
        use_sudo=True)
    upload_project(
        remote_dir='/srv/',
        local_dir=os.path.join(local_vendor_dir, 'formula-repos'),
        use_sudo=True)
    upload_project(
        remote_dir=remote_state_dir,
        local_dir=local_salt_dir,
        use_sudo=True)
    upload_project(
        remote_dir=remote_pillar_dir,
        local_dir=os.path.join(local_pillar_dir, env.environment, '.'),
        use_sudo=True)
    cf_sls = StringIO(yaml.dump(cfg))
    put(
        remote_path=os.path.join(
            remote_pillar_dir,
            'cloudformation.sls'),
        local_path=cf_sls,
        use_sudo=True)
