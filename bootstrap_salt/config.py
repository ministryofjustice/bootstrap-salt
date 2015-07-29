import os
import pkgutil

import bootstrap_cfn.config

from fabric.api import env

import yaml


class MyConfigParser(bootstrap_cfn.config.ConfigParser):

    def base_template(self):
        ret = super(MyConfigParser, self).base_template()
        ret.add_mapping('KMS', {'salt': {'key': env.kms_key_id}})
        return ret

    def get_ec2_userdata(self):
        ret = super(MyConfigParser, self).get_ec2_userdata()

        bs_path = os.path.dirname(pkgutil.get_loader('bootstrap_salt').filename)
        script = os.path.join(bs_path, './contrib/bootstrap.sh')
        files = {'write_files': [{'encoding': 'b64',
                                  'content': env.kms_data_key,
                                  'owner': 'root:root',
                                  'path': '/etc/salt.key.enc',
                                  'permissions': '0600'},
                                 {'content': open(script).read(),
                                  'owner': 'root:root',
                                  'path': '/tmp/bootstrap.sh',
                                  'permissions': '0700'}]}

        ret.append({
            'content': yaml.dump(files),
            'mime_type': 'text/cloud-config'
        })
        return ret