#!/usr/bin/env python

import math
import os
import sys
import yaml
import tempfile
import logging
import pkgutil
import gnupg
import base64
logging.basicConfig(level=logging.INFO)

import bootstrap_cfn.config as config
from fabric.api import env, task, local, get
from fabric.contrib import files
from bootstrap_cfn.fab_tasks import _validate_fabric_env, \
    get_stack_name, get_config, cfn_create

from ec2 import EC2
from bootstrap_salt.kms import KMS
import bootstrap_salt.utils as utils
from bootstrap_salt.config import MyConfigParser

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
# This overrides the config parser in bootstrap-cfn
# this allows us to inject extra userdata into the launch
# config of the auto scaling groups
env.cloudformation_parser = MyConfigParser


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


def get_kms_key_id():
    """
    Returns an id for a KMS master key with an alias of:
    application-environment. If no key exists it will create a
    new one.
    """
    alias = "{0}-{1}".format(env.application, env.environment)
    kms = get_connection(KMS)
    key_id = kms.get_key_id(alias)
    if not key_id:
        key_id = kms.create_key(alias)
    return key_id


def create_kms_data_key():
    """
    Returns an encrypted version of a new data key, generated
    by KMS. The encrypted blob can be decrypted in the future
    by anyone with the contents of the blob and access to the KMS
    master key via IAM.
    """
    kms = get_connection(KMS)
    return kms.generate_data_key(get_kms_key_id())

bcfn_create = cfn_create


@task
def cfn_create(test=False):
    """
    Here we override the cfn_create task from bootstrap_cfn so that we
    can inject the KMS key ID and encrypted key into the fabric environment.
    """
    env.kms_key_id = get_kms_key_id()
    env.kms_data_key = create_kms_data_key()
    bcfn_create(test=test)


def get_instance_ips():
    """
    Get a list of the public IPs of the current instances in the stack.
    """
    ec2 = get_connection(EC2)
    stack_name = get_stack_name()
    return ec2.get_stack_instance_public_ips(stack_name)


def get_ips_batch(fraction=None):
    '''
    Takes a list of ips and batches them
    in the format [['ip1','ip2']]
    If a fraction is specified the ips are split into batches sized by
    that fraction i.e. 4 ips with fraction=0.5 will return:
    [['ip1', 'ip2'],['ip3','ip4']]
    '''
    ips = get_instance_ips()
    if fraction:
        number_in_batch = int(math.ceil(len(ips)*float(fraction)))
        return [ips[i:i+number_in_batch] for i in xrange(0, len(ips), number_in_batch)]
    else:
        return [ips]


@task
def wait_for_minions(timeout=600, interval=20):
    """
    This task ensures that the initial bootstrap has finished on all
    stack instances.

    Args:
        timeout(int): time to wait for bootstrap to finish
        interval(int): time to wait inbetween checks
    """
    _validate_fabric_env()
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    print "Waiting for SSH on all instances..."
    ec2.wait_for_ssh(stack_name)
    fab_hosts = get_instance_ips()
    print "Waiting for bootstrap script to finish on all instances..."
    utils.timeout(timeout, interval)(is_bootstrap_done)(fab_hosts)


def is_bootstrap_done(hosts):
    """
    Loops through a list of IPs and checks for the prescence of
    /tmp/bootstrap_done to ensure that the launch config has finished
    executing.

    Args:
        hosts(list): A list of IPs to check
    """
    ret = []
    for host in hosts:
        env.host_string = '{0}@{1}'.format(env.user, host)
        ret.append(files.exists('/tmp/bootstrap_done'))
    return all(ret)


def get_connection(klass):
    """
    Helper method to get connection to AWS

    Args:
        klass(class): The AWS class to setup the connection to.
    """
    _validate_fabric_env()
    return klass(env.aws, env.aws_region)


@task
def upload_salt():
    """
    Get encrypted key from one of the stack hosts,
    Create tar file with salt states, pillar, formula etc.
    Encrypt tar using KMS and GPG(AES).
    Upload tar to S3.
    """
    _validate_fabric_env()
    stack_name = get_stack_name()

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
        env.environment,
        '.')
    local_vendor_dir = os.path.join(
        work_dir,
        salt_cfg.get('local_vendor_dir', 'vendor'),
        '.')

    remote_state_dir = salt_cfg.get('remote_state_dir', '/srv/salt')
    remote_pillar_dir = salt_cfg.get('remote_pillar_dir', '/srv/pillar')

    vendor_root = os.path.join(local_vendor_dir, '_root', '.')
    bs_path = pkgutil.get_loader('bootstrap_salt').filename
    dirs = {local_salt_dir: [remote_state_dir],
            local_pillar_dir: [remote_pillar_dir],
            vendor_root: [remote_state_dir, '/srv/formula-repos'],
            '{0}/contrib/srv/salt/_grains'.format(bs_path): [remote_state_dir],
            '{0}/contrib/etc/salt'.format(bs_path): ['/etc'],
            '{0}/salt_utils.py'.format(bs_path):
            ['/usr/local/bin/']
            }
    tmp_folder = tempfile.mkdtemp()
    for local_dir, dest_dirs in dirs.items():
        for dest_dir in dest_dirs:
            dest = os.path.join(tmp_folder, ".{0}".format(dest_dir))
            local("mkdir -p {0}".format(dest))
            local("cp -r {0} {1}".format(local_dir, dest))
    cfg_path = os.path.join(tmp_folder, "./{0}".format(remote_pillar_dir))
    with open(os.path.join(cfg_path, 'cloudformation.sls'), 'w') as cfg_file:
        yaml.dump(cfg, cfg_file)
    local("chmod -R 755 {0}".format(tmp_folder))
    local("chmod -R 700 {0}{1}".format(tmp_folder, remote_state_dir))
    local("chmod -R 700 {0}{1}".format(tmp_folder, remote_pillar_dir))
    local("tar -czvf ./srv.tar -C {0} .".format(tmp_folder))
    local("rm -rf {0}".format(tmp_folder))

    env.host_string = '{0}@{1}'.format(env.user, get_instance_ips()[0])
    # Here we get the encypted data key for this specific stack, we then use
    # KMS to get the plaintext key and use that key to encrypt the salt content
    # We get the key over SSH because it is unique to each stack.
    get(remote_path='/etc/salt.key.enc', local_path='./', use_sudo=True)
    encrypt_file('./srv.tar')
    local("rm ./salt.key.enc")

    local("rm -rf ./srv.tar")
    local("aws s3 --profile {0} cp ./srv.tar.gpg s3://{1}-salt/".format(env.aws,
          stack_name))
    local("rm -rf ./srv.tar.gpg")


@task
def encrypt_file(file_name):
    """
    Encrypt a file using an encrypted KMS data key using GPG with an AES256
    cipher. Output file_name.gpg

    Args:
        file_name(string): path of file to encrypt
    """
    kms = get_connection(KMS)
    key = kms.decrypt(open('./salt.key.enc').read())['Plaintext']
    key = base64.b64encode(key)
    gpg = gnupg.GPG()
    gpg.encrypt(open(file_name), passphrase=key, encrypt=False, symmetric='AES256',
                output=open('{0}.gpg'.format(file_name), 'w'))


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
