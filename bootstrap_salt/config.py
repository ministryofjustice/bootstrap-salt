import os
import pkg_resources
import pkgutil

from troposphere import Join, Ref
from troposphere.iam import PolicyType
from troposphere.s3 import Bucket

from bootstrap_cfn.config import ConfigParser

from fabric.api import env

import yaml


class MyConfigParser(ConfigParser):

    def __init__(self, *args, **kwargs):
        try:
            self.kms_key_id = env.kms_key_id
            self.kms_data_key = env.kms_data_key
        except AttributeError:
            pass
        super(MyConfigParser, self).__init__(*args, **kwargs)

    def base_template(self):
        ret = super(MyConfigParser, self).base_template()

        salt_bucket = Bucket(
            "SaltBucket",
            AccessControl="BucketOwnerFullControl",
            BucketName="{0}-salt".format(self.stack_name)
        )
        ret.add_resource(salt_bucket)

        arn = Join("", ["arn:aws:s3:::", Ref(salt_bucket), "/*"])
        salt_bucket_policy = {
            'Action': ['s3:Get*',
                       's3:List*'],
            "Resource": arn,
            'Effect': 'Allow'}
        salt_role_policy = PolicyType(
            "S3SaltPolicy",
            PolicyName="S3SaltPolicy",
            PolicyDocument={"Statement": [salt_bucket_policy]},
            Roles=[Ref("BaseHostRole")],
        )
        ret.add_resource(salt_role_policy)

        arn = Join("", ["arn:aws:kms:", Ref('AWS::Region'),
                        ':',
                        Ref('AWS::AccountId'),
                        ':key/',
                        self.kms_key_id])
        kms_policy = {
            "Sid": "AllowUseOfTheKey",
            "Effect": "Allow",
            "Action": [
                "kms:Decrypt",
                "kms:DescribeKey"
            ],
            "Resource": arn
        }
        kms_role_policy = PolicyType(
            "KMSPolicy",
            PolicyName="KMSPolicy",
            PolicyDocument={"Statement": [kms_policy]},
            Roles=[Ref("BaseHostRole")],
        )
        ret.add_resource(kms_role_policy)

        return ret

    def get_ec2_userdata(self):
        self.__version__ = pkg_resources.get_distribution("bootstrap_salt").version
        ret = super(MyConfigParser, self).get_ec2_userdata()

        bs_path = pkgutil.get_loader('bootstrap_salt').filename
        script = os.path.join(bs_path, './contrib/bootstrap.sh')
        files = {'write_files': [{'encoding': 'b64',
                                  'content': self.kms_data_key,
                                  'owner': 'root:root',
                                  'path': '/etc/salt.key.enc',
                                  'permissions': '0600'},
                                 {'content': open(script).read(),
                                  'owner': 'root:root',
                                  'path': '{}/bootstrap.sh'.format(env.bootstrap_script_path),
                                  'permissions': '0700'}]}
        commands = {'runcmd': ['{}/bootstrap.sh v{}'.format(env.bootstrap_script_path, self.__version__)]}
        ret.append({
            'content': yaml.dump(commands),
            'mime_type': 'text/cloud-config'
        })
        ret.append({
            'content': yaml.dump(files),
            'mime_type': 'text/cloud-config'
        })
        return ret
