#!/usr/bin/env python

import os
from StringIO import StringIO
import sys
import random
import yaml
import json
import logging
logging.basicConfig(level=logging.INFO)

import bootstrap_cfn.config as config
from fabric.api import env, task, sudo, put, run, local
from fabric.contrib.project import upload_project
import dns.resolver
from bootstrap_cfn.fab_tasks import _validate_fabric_env, \
    get_stack_name, get_config

from cloudformation import Cloudformation
from ec2 import EC2
from bootstrap_cfn.r53 import R53

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
def aws(profile_name):
    """
    Set the AWS account to use

    Sets the environment variable 'aws' to the name of the
    account to use in the AWS config file (~/.aws/credentials.yaml)

    Args:
        profile_name(string): The string to set the environment
        variable to
    """
    env.aws = str(profile_name).lower()


@task
def environment(environment_name):
    """
    Set the environment section to be read from the project config
    file

    Sets the environment variable 'environment'.
    The named section will be read from the project's YAML file

    Args:
        environment_name(string): The string to set the
        variable to
    """
    env.environment = str(environment_name).lower()


@task
def tag(tag):
    """
    Set a tag for the stack

    Sets the environment variable 'tag'
    This gets used to store a DNS entry to identify
    multiple stacks with the same name.
    e.g. you can tag a stack as active, or inactive,
    green or blue etc.

    Args:
        tag(string): The string to set the
        variable to
    """
    env.tag = str(tag).lower()


@task
def application(application_name):
    """
    Set the application name

    Sets the environment variable 'application' to
    an application name. Which is just a name to
    associate with Cloudformation stack

    Args:
        application_name(string): The string to set the
        variable to
    """
    env.application = str(application_name).lower()


@task
def setup(salt_version='v2014.7.5'):
    """
    Setup the salt master and minions

    Call install_master and install_minions to setup salt
    """
    install_master(salt_version)
    install_minions(salt_version)


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
def swap_masters(tag1, tag2):
    """
    Swap two tagged stacks.
    """
    cfn_config = get_config()
    r53_conn = get_connection(R53)
    try:
        zone_name = cfn_config.data['master_zone']
    except KeyError:
        logging.warn("master_zone not found in config file, "
                     "so cannot swap master tags as they do "
                     "not exist. Recreate stacks after adding "
                     "master zone to the yaml config.")
        sys.exit(1)
    zone_id = r53_conn.get_hosted_zone_id(zone_name)
    master1 = 'master.{0}.{1}.{2}'.format(tag1,
                                          env.environment,
                                          env.application)
    master2 = 'master.{0}.{1}.{2}'.format(tag2,
                                          env.environment,
                                          env.application)
    master_ip_1 = r53_conn.get_record(zone_name, zone_id, master1, 'A')
    master_ip_2 = r53_conn.get_record(zone_name, zone_id, master2, 'A')
    fqdn1 = "{0}.{1}".format(master1, zone_name)
    fqdn2 = "{0}.{1}".format(master2, zone_name)
    r53_conn.update_dns_record(zone_id, fqdn1, 'A', master_ip_2)
    r53_conn.update_dns_record(zone_id, fqdn2, 'A', master_ip_1)
    local('ssh-keygen -R {0}'.format(fqdn1))
    local('ssh-keygen -R {0}'.format(fqdn2))


def find_master():
    """
    Find and return the FQDN of the salt master

    Search for the salt masters zone within the project config
    file, and then AWS if necessary, returning the fully
    qualified domain name of the salt master
    """
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
    if not hasattr(env, 'tag'):
        env.tag = 'active'
    try:
        master = 'master.{0}.{1}.{2}.{3}'.format(env.tag,
                                                 env.environment,
                                                 env.application,
                                                 zone_name)
        dns.resolver.query(master, 'A')
    except dns.resolver.NXDOMAIN:
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
    if hasattr(env, 'tag'):
        dns_name = 'master.{0}.{1}.{2}.{3}'.format(env.tag,
                                                   env.environment,
                                                   env.application,
                                                   zone_name)
    else:
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


def install_minions(salt_version):
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
        sudo('/tmp/bootstrap-salt.sh -A {0} -p python-boto git '
             '{1}'.format(master_prv_ip, salt_version))
        env.host_string = 'ubuntu@%s' % master_public_ip
        sudo('salt-key -y -A')

        # Once we've installed, then set the tag so we don't install again
        ec2.set_instance_tags([instance.id], {'SaltMasterPrvIP': master_prv_ip})


def install_master(salt_version):
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
    sudo('/tmp/bootstrap-salt.sh -M -A {0} -p python-boto git '
         '{1}'.format(master_prv_ip, salt_version))
    sudo('salt-key -y -A')


@task
def rsync():
    """
    Upload the salt data directories to the salt master

    Find the salt master, then upload the salt root directory,
    the pillar data, and the vendor formulas directory setup
    by salt-shaker.
    """
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
    """
    Generate the ssh key pillar from the github users data in the
    project config file

    Using the github_users entry from the project config file,
    this will get the corresponding keys from github and generate
    a set of users with admin privileges, outputting them to
    the pillar file.

    https://github.com/ministryofjustice/bootstrap-salt#github-based-ssh-key-generation

    Args:
        force(bool): True to ignore the existing key file
        strict(bool): True to remove all users not found in github
    """
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


@task
def check_admins_exist():
    """
    Check that we have set some admins in the pillar, exit with error code 1 if not

    Return:
        bool: True if admins exist in pillar, False otherwise
    """
    env.host_string = '{0}@{1}'.format(env.user, find_master())
    admins_json = sudo('/usr/bin/salt-call pillar.get admins --out=json 2> /dev/null', shell=False)
    admins_list = json.loads(admins_json).get('local', {}).keys()
    if not len(admins_list) > 0:
        link = "https://github.com/ministryofjustice/bootstrap-salt#github-based-ssh-key-generation"
        logging.error(("check_admins_exist: No admins found in pillar, please create them, see '%s'"
                       % (link)))
        return False
    logging.info(("check_admins_exist: Found admins in pillar, '%s'"
                  % (', '.join(admins_list))))
    return True
