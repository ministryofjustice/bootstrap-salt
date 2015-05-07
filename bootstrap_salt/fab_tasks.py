#!/usr/bin/env python

import os
from StringIO import StringIO
import sys
import random
import yaml
import logging
logging.basicConfig(level=logging.INFO)

from fabric.api import env, task, sudo, put, run
from fabric.contrib.project import upload_project
from cloudformation import Cloudformation
from ec2 import EC2
from r53 import R53
import bootstrap_cfn.config as config
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
def setup(stack_name=None):
    install_master()
    install_minions()


def get_connection(klass):
    _validate_fabric_env()
    return klass(env.aws, env.aws_region)


def get_master_ip():
    _validate_fabric_env()
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    master = ec2.get_master_instance(stack_name).ip_address
    print 'Salt master public address: {0}'.format(master)
    return master


@task
def find_master():
    _validate_fabric_env()
    project_config = config.ProjectConfig(env.config,
                                          env.environment,
                                          env.stack_passwords)
    cfg = project_config.config
    try:
        zone_name = cfg['master_zone']
    except KeyError:
        logging.warn("master_zone not found in config file, "
                     "so DNS discovery of master not possible, "
                     "falling back to AWS EC2 API.")
        return get_master_ip()
    master = 'master.{0}.{1}.{2}'.format(env.environment,
                                         env.application,
                                         zone_name)
    return master


def set_master_dns():
    master_ip = get_master_ip()
    project_config = config.ProjectConfig(env.config,
                                          env.environment,
                                          env.stack_passwords)
    cfg = project_config.config
    try:
        zone_name = cfg['master_zone']
    except KeyError:
        logging.warn("master_zone not found in config file, "
                     "no DNS entry will be created, you will "
                     "need AWS access to deploy etc.")
        return False
    r53 = get_connection(R53)
    zone_id = r53.get_hosted_zone_id(zone_name)
    dns_name = 'master.{0}.{1}.{2}'.format(env.environment,
                                           env.application,
                                           zone_name)
    r53.update_dns_record(zone_id, dns_name, 'A', master_ip)
    return True


def get_candidate_minions(stack_name):
    cfn = get_connection(Cloudformation)
    ec2 = get_connection(EC2)
    instance_ids = cfn.get_stack_instance_ids(stack_name)
    master_instance_id = ec2.get_master_instance(stack_name).id
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
    to_install = list(set(candidates).difference(set(
        [x.id for x in existing_minions])))
    if not to_install:
        return
    public_ips = ec2.get_instance_public_ips(to_install)
    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    master_inst = ec2.get_master_instance(stack_name)
    master_public_ip = master_inst.ip_address
    master_prv_ip = master_inst.private_ip_address
    ec2.set_instance_tags(to_install, {'SaltMasterPrvIP': master_prv_ip})
    for inst_ip in public_ips:
        env.host_string = 'ubuntu@%s' % inst_ip
        # copy the salt_utils.py from local to EC2 and chmod it
        d = os.path.dirname(__file__)
        saltutils = d + "/salt_utils.py"
        if not os.path.isfile(saltutils):
            print "ERROR: Cannot find %s" % saltutils
            sys.exit(1)
        put(saltutils, '/usr/local/bin', use_sudo=True)
        sudo('chmod 755 /usr/local/bin/salt_utils.py')
        run('wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' % sha)
        sudo('chmod 755 /tmp/bootstrap-salt.sh')
        sudo('/tmp/bootstrap-salt.sh -A ' + master_prv_ip + ' -p python-boto git v2014.1.4')
        env.host_string = 'ubuntu@%s' % master_public_ip
        sudo('salt-key -y -A')


def install_master():
    _validate_fabric_env()
    stack_name = get_stack_name()
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
    set_master_dns()

    env.host_string = 'ubuntu@%s' % master_public_ip
    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    # copy the salt_utils.py from local to EC2 and chmod it
    d = os.path.dirname(__file__)
    saltutils = d + "/salt_utils.py"
    if not os.path.isfile(saltutils):
        print "ERROR: Cannot find %s" % saltutils
        sys.exit(1)
    put(saltutils, '/usr/local/bin', use_sudo=True)
    sudo('chmod 755 /usr/local/bin/salt_utils.py')
    run('wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' % sha)
    sudo('chmod 755 /tmp/bootstrap-salt.sh')
    sudo('/tmp/bootstrap-salt.sh -M -A ' + master_prv_ip + ' -p python-boto git v2014.1.4')
    sudo('salt-key -y -A')


@task
def rsync():
    _validate_fabric_env()
    work_dir = os.path.dirname(env.real_fabfile)
    project_config = config.ProjectConfig(env.config,
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
