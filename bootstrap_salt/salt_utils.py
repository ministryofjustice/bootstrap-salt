#!/usr/bin/env python
import base64
import os
import subprocess
import sys

import salt
import salt.client
import salt.config
import salt.output
import salt.runner


class BootstrapUtilError(Exception):

    def __init__(self, msg):
        print >> sys.stderr, "[ERROR] {0}: {1}".format(self.__class__.__name__, msg)


class SaltStateError(BootstrapUtilError):
    pass


class SaltParserError(BootstrapUtilError):
    pass


def get_salt_data():
    import boto.s3
    import boto.kms
    import gnupg
    import shutil

    caller = salt.client.Caller()
    stack_name = caller.function('grains.item', 'aws:cloudformation:stack-name')['aws:cloudformation:stack-name']
    region = caller.function('grains.item', 'aws_region')['aws_region']
    kms = boto.kms.connect_to_region(region)
    s3 = boto.s3.connect_to_region(region)
    tar_file = s3.get_bucket('{0}-salt'.format(stack_name)).get_key('srv.tar.gpg')
    if tar_file:
        tar_file.get_contents_to_filename('/srv.tar.gpg')
        os.chmod('/srv.tar.gpg', 0700)
        key = kms.decrypt(open('/etc/salt.key.enc').read())['Plaintext']
        key = base64.b64encode(key)
        gpg = gnupg.GPG()
        gpg.decrypt_file(open('/srv.tar.gpg'), passphrase=key,
                         output='/srv.tar')
        os.chmod('/srv.tar', 0700)
    if not tar_file and not os.path.isfile('/srv.tar'):
        print "Salt tar not found, probably this is an initial bootstrap"
        sys.exit(0)
    shutil.rmtree('/srv/salt', ignore_errors=True)
    shutil.rmtree('/srv/pillar', ignore_errors=True)
    subprocess.call(['tar', '--no-same-owner', '-xvf', '/srv.tar', '-C', '/'])


def highstate():
    '''
    Raises:
        SaltParserError: if any minion cannot execute the state
        SaltStateError: if any state execution returns False
    '''
    get_salt_data()
    caller = salt.client.Caller()
    # synchronizes custom modules, states, beacons, grains, returners,
    # output modules, renderers, and utils.
    caller.function('saltutil.sync_all')
    res = caller.function('state.highstate')
    return check_state_result(res)


def state(state):
    '''
    Raises:
        SaltParserError: if any minion cannot execute the state
        SaltStateError: if any state execution returns False
    Args:
        state(string): the state to run
    '''
    get_salt_data()
    caller = salt.client.Caller()
    res = caller.function('state.sls', state)
    return check_state_result(res)


def check_state_result(result):
    '''
    Takes a salt results dictionary, prints the ouptut in salts highstate ouput
    format and checks all states executed successfully. Returns True or raises:
    Raises:
        SaltParserError: if any minion cannot execute the state
        SaltStateError: if any state execution returns False
    Args:
        result(dict): salt results dictionary
    '''
    __opts__ = salt.config.minion_config('/etc/salt/minion')
    salt.output.display_output({'local': result}, out='highstate', opts=__opts__)
    if isinstance(result, dict):
        results = [v['result'] for v in result.values()]
    else:
        raise SaltParserError('Minion could not parse state data')
    if all(results):
        return True
    else:
        raise SaltStateError('State did not execute successfully')

if __name__ == "__main__":
    import argparse

    from salt.log.setup import setup_console_logger, setup_logfile_logger

    parser = argparse.ArgumentParser(description='Run salt states')
    parser.add_argument('-s', dest='state', type=str,
                        help='Name of state or "highstate"', required=True)

    setup_console_logger(log_level='info')
    setup_logfile_logger(log_path='/var/log/salt/minion', log_level='debug')

    args = parser.parse_args()
    if args.state == "highstate":
        highstate()
    else:
        state(args.state)
