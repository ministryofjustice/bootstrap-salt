#!/usr/bin/env python

import os
from StringIO import StringIO
import sys
import random
import yaml
import logging
logging.basicConfig(level=logging.INFO)

import bootstrap_cfn.config as config
from fabric.api import env, task, sudo, put, run
from fabric.contrib.project import upload_project
from bootstrap_cfn.fab_tasks import _validate_fabric_env, \
    get_stack_name, get_config

from cloudformation import Cloudformation
from ec2 import EC2
from r53 import R53

from .deploy_lib import github

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


def put_util_script():
    # copy the salt_utils.py from local to EC2 and chmod it
    d = os.path.dirname(__file__)
    saltutils = d + "/salt_utils.py"
    if not os.path.isfile(saltutils):
        print "ERROR: Cannot find %s" % saltutils
        sys.exit(1)
    put(saltutils, '/usr/local/bin', use_sudo=True)
    sudo('chmod 755 /usr/local/bin/salt_utils.py')


def install_minions():
    _validate_fabric_env()
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    print "Waiting for SSH on all instances..."
    ec2.wait_for_ssh(stack_name)

    master_inst = ec2.get_master_instance(stack_name)
    master_public_ip = master_inst.ip_address
    master_prv_ip = master_inst.private_ip_address

    to_install = ec2.get_unconfigured_minions(stack_name, master_prv_ip)

    if not to_install:
        return

    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    for instance in to_install:

        env.host_string = 'ubuntu@%s' % instance.ip_address

        put_util_script()
        run('wget https://raw.githubusercontent.com/saltstack/salt-bootstrap/%s/bootstrap-salt.sh -O /tmp/bootstrap-salt.sh' % sha)
        sudo('chmod 755 /tmp/bootstrap-salt.sh')
        sudo('/tmp/bootstrap-salt.sh -A ' + master_prv_ip + ' -p python-boto git v2014.1.4')

        env.host_string = 'ubuntu@%s' % master_public_ip
        sudo('salt-key -y -A')

        # Once we've installed, then set the tag so we don't install again
        ec2.set_instance_tags([instance.id], {'SaltMasterPrvIP': master_prv_ip})


def install_master():
    _validate_fabric_env()
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    cfn = get_connection(Cloudformation)
    print "Waiting for SSH on all instances..."
    ec2.wait_for_ssh(stack_name)

    master_inst = ec2.get_master_instance(stack_name)
    if master_inst:
        master = master_inst.id
    else:
        instance_ids = cfn.get_stack_instance_ids(stack_name)
        master = random.choice(instance_ids)

    master_prv_ip = ec2.get_instance_private_ips([master])[0]
    master_public_ip = ec2.get_instance_public_ips([master])[0]
    ec2.set_instance_tags(master, {'SaltMaster': 'True', 'SaltMasterPrvIP': master_prv_ip})
    set_master_dns()

    env.host_string = 'ubuntu@%s' % master_public_ip
    sha = '6080a18e6c7c2d49335978fa69fa63645b45bc2a'
    put_util_script()
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
    put_util_script()
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


@task(alias='ssh_keys')
def generate_ssh_key_pillar(force=False, strict=True):
    # force: ignore existing key file
    # strict: remove all users not found in github
    work_dir = os.path.dirname(env.real_fabfile)

    config = get_config()
    salt_cfg = config.data.get('salt', {})

    local_pillar_dir = os.path.join(
        work_dir, salt_cfg.get('local_pillar_dir', 'pillar'))
    pillar_file = os.path.join(local_pillar_dir, env.environment, 'keys.sls')
    key_config = config.data.get('github_users', {})
    ssh_key_data = github.get_keys(key_config)

    if os.path.exists(pillar_file) and not force:
        with open(pillar_file) as pf_handle:
            user_data = yaml.load(pf_handle)
            current_admins = set(user_data.get('admins', {}).keys())
    else:
        current_admins = set()

    if current_admins == set(ssh_key_data.keys()):
        return

    if strict and current_admins:
        to_be_removed = current_admins - set(ssh_key_data.keys())
        if (float(len(to_be_removed))/float(len(current_admins))) * 100 > 50.00:
            print 'WARNING: Removing more than 50% of the current users.'
        for absent_user in to_be_removed:
            print 'Setting {} to absent.'.format(absent_user)
            ssh_key_data.update({absent_user: {'absent': True}})

    result = {'admins': ssh_key_data}
    yaml.dump(result, open(pillar_file, 'w'), default_flow_style=False)
