#!/usr/bin/env python
import argparse
from salt.log.setup import setup_console_logger, setup_logfile_logger

import boto.s3
import boto.kms
import gnupg
import shutil

import base64
import logging
import os
import sys

import salt
import salt.client
import salt.config
import tarfile

# Set up the logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap-salt::salt_utils_update")
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger('boto').setLevel(logging.CRITICAL)


class SaltUtilsUpdateWrapper():
    """
    Class to wrap the s3 downloading and data synchronising of salt
    data.
    """
    caller = None
    kms_connection = None
    s3_connection = None

    def __init__(self):
        self.caller = salt.client.Caller()

    def get_salt_data(self):
        """
        Download the salt configuration and support files from an S3
        bucket and extract them to the correct folder.
        """
        logger.info("get_salt_data: Getting remote salt data...")

        # Set up the connection to AWS
        logger.info("get_salt_data: Setting up AWS connection...")
        stack_name_grain = self.caller.function(
            'grains.item',
            'aws:cloudformation:stack-name'
        )
        stack_name = stack_name_grain[
            'aws:cloudformation:stack-name'
        ]
        region = self.caller.function('grains.item',
                                      'aws_region')['aws_region']
        self.kms_connection = boto.kms.connect_to_region(region)
        self.s3_connection = boto.s3.connect_to_region(region)

        # If the s3 stored tar file exists, download it and decrypt
        bucket_name = '{0}-salt'.format(stack_name)
        logger.info("get_salt_data: Getting salt data from s3 bucket: {}"
                    .format(bucket_name))
        tar_file = self.s3_connection.get_bucket(bucket_name).get_key('srv.tar.gpg')
        if tar_file:
            logger.info("get_salt_data: Found tar file: {}"
                        .format(tar_file))
            tar_file.get_contents_to_filename('/srv.tar.gpg')
            os.chmod('/srv.tar.gpg', 0700)
            self.decrypt_salt_data()
            os.chmod('/srv.tar', 0700)
        # If this stack has not been highstated yet, no tar file will
        # be available
        if not tar_file and not os.path.isfile('/srv.tar'):
            logger.warning("get_salt_data: Salt tar not found, "
                           "probably this is an initial bootstrap")
            sys.exit(0)

        # Delete the previous configuration files and extract the new
        logger.info("get_salt_data: Deleting previous salt config...")
        shutil.rmtree('/srv/salt', ignore_errors=True)
        shutil.rmtree('/srv/pillar', ignore_errors=True)
        logger.info("get_salt_data: Extracting tar file...".format(tar_file))
        self.untar(filename='/srv.tar', path='/')
        logger.info("get_salt_data: Extracted tar file...".format(tar_file))

    def untar(self, filename, path='/'):
        """
        Untar a tar file into the specified path

        Args:
            filename(string): The name of the tar file
            path(string): The path to extract into
        """
        logger.info("untar: Untarring file '{}' to path '{}'..."
                    .format(filename, path))
        with tarfile.open(filename, "r") as tar:
            for tarinfo in tar:
                logger.info('untar: Extracting {}'.format(tarinfo.name))
                tarinfo.uid = tarinfo.gid = 0
                tarinfo.uname = tarinfo.gname = "root"
            tar.extractall(path=path)
        logger.info("untar: Tar file extracted")

    def decrypt_salt_data(self,
                          input_file='/srv.tar.gpg',
                          output_file='/srv.tar',
                          key_file='/etc/salt.key.enc'):
        """
        Decrypt the salt data

        Args:
            input_file(string): The path to the file containing the encrypted data
            output_file(string): The path to the file to save the decrypted output to
            key_file(string): The path to the file containing the key to use
        """
        key = self.kms_connection.decrypt(open(key_file).read())['Plaintext']
        key = base64.b64encode(key)
        gpg = gnupg.GPG()
        gpg.decrypt_file(open(input_file),
                         passphrase=key,
                         output=output_file)

    def sync_remote_salt_data(self, clear_cache=True):
        """
        Synchronise the remote salt data.
        """
        logger.info("sync_remote_salt_data: Synchronising remote data...")

        # Fetch the remote salt data
        self.get_salt_data()

        if clear_cache:
            # Clear minions cache for new data
            cache_clear_result = self.caller.function('saltutil.clear_cache')
            logger.info("sync_remote_salt_data: Cleared minion cache: {}"
                        .format(cache_clear_result))
        # synchronizes custom modules, states, beacons, grains, returners,
        # output modules, renderers, and utils.
        sync_result = self.caller.function('saltutil.sync_all', 'refresh=True')
        logger.info("sync_remote_salt_data: "
                    "Synchronised dynamic module data: {}"
                    .format(sync_result))
        return sync_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run salt states')
    parser.add_argument('--loglevel',
                        dest='loglevel',
                        type=str,
                        help='Level of logging detail',
                        default="info")
    args = parser.parse_args()
    setup_console_logger(log_level=args.loglevel)
    setup_logfile_logger(log_path='/var/log/salt/minion',
                         log_level=args.loglevel)

    salt_utils_update_wrapper = SaltUtilsUpdateWrapper()
    salt_utils_update_wrapper.sync_remote_salt_data()
