#!/usr/bin/env python

from functools import wraps
import json
import math
import os
from pipes import quote
import StringIO
import sys
import yaml
import tempfile
import logging
import pkgutil
import gnupg
import base64
import shutil

import bootstrap_cfn.config as config
from fabric.api import env, execute, parallel, task, local, get, settings, sudo
from fabric.contrib import files
import fabric.decorators
from fabric.exceptions import NetworkError
from bootstrap_cfn.fab_tasks import _validate_fabric_env, \
    get_stack_name, get_basic_config, cfn_create, cfn_delete

from ec2 import EC2
from bootstrap_salt.kms import KMS
import bootstrap_salt.utils as utils
from bootstrap_salt.config import MyConfigParser

from .deploy_lib import github

# Setup logging
logging.basicConfig(level=logging.INFO)

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

# Set the default bootstrap.sh location
env.bootstrap_script_path = '/usr/local/bin'
env.bootstrap_tmp_path = '/tmp'


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

bcfn_create, bcfn_delete = cfn_create, cfn_delete


@task
@wraps(bcfn_create)
def cfn_create(*args, **kwargs):
    """
    Here we override the cfn_create task from bootstrap_cfn so that we
    can inject the KMS key ID and encrypted key into the fabric environment.
    """
    env.kms_key_id = get_kms_key_id()
    env.kms_data_key = create_kms_data_key()
    bcfn_create(*args, **kwargs)


@task
@wraps(bcfn_delete)
def cfn_delete(*args, **kwargs):
    pre_delete_callbacks = kwargs.pop('pre_delete_callbacks', [])
    pre_delete_callbacks.append(delete_tar)
    bcfn_delete(*args, pre_delete_callbacks=pre_delete_callbacks, **kwargs)


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
        number_in_batch = int(math.ceil(len(ips) * float(fraction)))
        return [ips[i: (i + number_in_batch)] for i in xrange(0, len(ips), number_in_batch)]
    else:
        return [ips]


@task
def wait_for_minions(timeout=600, interval=20):
    """
    This task ensures that the initial bootstrap has finished on all
    stack instances.

    Args:
        timeout(int): time to wait for bootstrap to finish
        interval(int): time to wait in-between checks
    """
    _validate_fabric_env()
    stack_name = get_stack_name()
    ec2 = get_connection(EC2)
    logging.info("Waiting for SSH on all instances...")
    ec2.wait_for_ssh(stack_name)
    fab_hosts = get_instance_ips()
    logging.info("Waiting for bootstrap script to finish on all instances...")
    utils.timeout(timeout, interval)(is_bootstrap_done)(fab_hosts)


def is_bootstrap_done(hosts):
    """
    Loops through a list of IPs and checks for the prescence of
    /tmp/bootstrap_done to ensure that the launch config has finished
    executing. The call will also try to handle the case where we lose
    ssh during the wait, which can happen if another action triggers
    a reboot.

    Args:
        hosts(list): A list of IPs to check
    """
    ret = []
    for host in hosts:
        env.host_string = '{0}@{1}'.format(env.user, host)
        target_file = '{}/bootstrap_done'.format(env.bootstrap_tmp_path)
        try:
            file_exists = files.exists(target_file)
            ret.append(file_exists)
            if file_exists:
                logging.info("Salt bootstrap file {} on host {}..."
                             .format(target_file, host))
            else:
                logging.info("Salt bootstrap file {} not found on host {}..."
                             .format(target_file, host))
        except NetworkError:
            logging.warning("Could not connect to host {}, attempting to recover connection..."
                            .format(host))
            # Catch a network error and try again
            stack_name = get_stack_name()
            ec2 = get_connection(EC2)
            ec2.wait_for_ssh(stack_name)
    return all(ret)


def get_connection(klass):
    """
    Helper method to get connection to AWS

    Args:
        klass(class): The AWS class to setup the connection to.
    """
    _validate_fabric_env()
    return klass(env.aws, env.aws_region)


# This is the fab task. It can be called as stand alone from ``fab salt.delete_tar``
@task(name='delete_tar')
def delete_tar_task():
    """
    Remove the encrypted salt tree from the s3 bucket.

    This needs to be called before invoking cfn_delete otherwise the S3 bucket
    will fail to be deleted. This will only delete the one file the
    ``upload_salt`` task creates so if any other files are placed in there then
    this task will still fail.
    """
    _validate_fabric_env()
    stack_name = get_stack_name()
    delete_tar(stack_name=stack_name)


# This is passed as a callback fn to cfn_delete that respects it's confirmation behaviour.
def delete_tar(stack_name, **kwargs):
    with settings(warn_only=True):
        local("aws s3 --profile {0} rm s3://{1}-salt/srv.tar.gpg".format(quote(env.aws), quote(stack_name)))


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
        )
    local_pillar_dir = os.path.join(
        work_dir,
        salt_cfg.get('local_pillar_dir', 'pillar'),
        env.environment,
        )
    local_vendor_dir = os.path.join(
        work_dir,
        salt_cfg.get('local_vendor_dir', 'vendor'),
        )

    # TODO: This patth actuall appears in the minion conf which isn't
    # templated, so die if this path is different (it's better to error
    # explicitly than just not work.
    remote_state_dir = salt_cfg.get('remote_state_dir', '/srv/salt')
    remote_pillar_dir = salt_cfg.get('remote_pillar_dir', '/srv/pillar')

    vendor_root = os.path.join(local_vendor_dir, '_root')
    bs_path = pkgutil.get_loader('bootstrap_salt').filename
    dirs = {local_salt_dir: remote_state_dir,
            local_pillar_dir: remote_pillar_dir,
            vendor_root: '/srv/salt-formulas/',
            '{0}/contrib/srv/salt/_grains'.format(bs_path): os.path.join(remote_state_dir, "_grains", ""),
            '{0}/contrib/etc/'.format(bs_path): '/etc/',
            '{0}/contrib/usr/'.format(bs_path): '/usr/',
            }

    tmp_folder = tempfile.mkdtemp()
    for local_dir, dest_dir in dirs.items():
        # Since dest dir will likely start with "/" (which would make join then
        # ignore the tmp_folder we speciffy) make it start with "./" instead so
        # it is contained
        stage_path = os.path.join(tmp_folder, "." + dest_dir)

        utils.copytree(local_dir, stage_path, symlinks=False)

    cfg_path = os.path.join(tmp_folder, "./{0}".format(remote_pillar_dir))
    with open(os.path.join(cfg_path, 'cloudformation.sls'), 'w') as cfg_file:
        yaml.dump(cfg, cfg_file)

    local("chmod -R 755 {0}".format(tmp_folder))
    local("chmod -R 700 {0}{1}".format(tmp_folder, quote(remote_state_dir)))
    local("chmod -R 700 {0}{1}".format(tmp_folder, quote(remote_pillar_dir)))

    shutil.make_archive("srv",
                        format="tar",
                        root_dir=tmp_folder)
    shutil.rmtree(tmp_folder)

    env.host_string = '{0}@{1}'.format(env.user, get_instance_ips()[0])
    # Here we get the encypted data key for this specific stack, we then use
    # KMS to get the plaintext key and use that key to encrypt the salt content
    # We get the key over SSH because it is unique to each stack.

    key = StringIO.StringIO()

    get(remote_path='/etc/salt.key.enc', local_path=key, use_sudo=True)
    key.seek(0)
    encrypt_file('./srv.tar', key_file=key)
    key.close()

    os.unlink("srv.tar")
    local("aws s3 --profile {0} cp ./srv.tar.gpg s3://{1}-salt/".format(quote(env.aws), quote(stack_name)))
    os.unlink("srv.tar.gpg")


@task
def encrypt_file(file_name, key_file="./salt.key.enc"):
    """
    Encrypt a file using an encrypted KMS data key using GPG with an AES256
    cipher. Output file_name.gpg

    Args:
        file_name(string): path of file to encrypt
        key_file(string): path to encrypted key. Contents will be read and
            decrypted using KMS
    """
    kms = get_connection(KMS)
    if isinstance(key_file, basestring):
        key_file = open(key_file)
    key = kms.decrypt(key_file.read())['Plaintext']
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

    # ssh key lookup only needs the basic configuration data in
    # the local config.
    basic_config = get_basic_config()
    salt_cfg = basic_config.get('salt', {})
    key_config = basic_config.get('github_users', {})

    local_pillar_dir = os.path.join(
        work_dir, salt_cfg.get('local_pillar_dir', 'pillar'))
    pillar_file = os.path.join(local_pillar_dir, env.environment, 'keys.sls')

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
        if (float(len(to_be_removed)) / float(len(current_admins))) * 100 > 50.00:
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
        bool: True if admins exist in the pillars of all available instances,
            False otherwise
    """
    # Find all instance ips and check admins on all of them. If one
    # instance lacks admins then the check fails
    host_ips = get_instance_ips()
    for host_ip in host_ips:
        # Create a host string for the instance
        host = '{0}@{1}'.format(env.user, host_ip)
        env.host_string = host
        # Load the admins pillar data
        admins_json = sudo('/usr/bin/salt-call pillar.get admins --out=json 2> /dev/null',
                           shell=False)
        admins_dict = json.loads(admins_json).get('local', {})
        # If we have no admins data in 'local' then we have no admins
        # We also assume that we have admins if we have *any* data, a
        # simplistic test
        if len(admins_dict) <= 0:
            link = "https://github.com/ministryofjustice/bootstrap-salt#github-based-ssh-key-generation"
            logging.error(("check_admins_exist: No admins found in pillar on host '%s', "
                           "please create them, see '%s'. "
                           "Default user removal will be skipped until admins are set."
                           % (host_ip, link)))
            return False

        logging.info(("check_admins_exist: Found admins '%s' on host '%s'"
                      % (', '.join(admins_dict.keys()),
                         host_ip)))
    return True


@task
def upgrade_packages(packages, fraction=None, restart=False):
    """
    Upgrade the packages specified, optionally rebooting afterwards

    Args:
        packages(list): List of packages to update. These can be a simple list
            or with package versions, for example
            '["package1", "package2"]' - get the latest versions of package1 and package2
            '["package1", {"package2", "1.2.3"}]' - get the latest versions of package1,
                and version 1.2.3 of package2.
        fraction(float): The decimal fraction of minions to deploy to None means
            all in one batch
        restart(bool): False to not reboot after installation, True to reboot the instance.
    """
    for batch in get_ips_batch(fraction):
        rup = fabric.decorators.hosts(batch)(run_upgrade_packages)
        execute(rup, packages, fraction, restart)


@parallel
def run_upgrade_packages(packages, fraction=None, restart=False):
    state = "pkg.install refresh=True only_upgrade=True pkgs='{}'".format(packages)
    if fraction:
        sudo('/usr/bin/salt-call {}'.format(state), shell=False)
        if restart:
            sudo('/usr/bin/salt-call system.reboot', shell=False)
    else:
        sudo('/usr/bin/salt-call {}'.format(state), shell=False)
        if restart:
            sudo('/usr/bin/salt-call system.reboot', shell=False)
