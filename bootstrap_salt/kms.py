import base64

from bootstrap_cfn import utils

import boto.kms


class KMS:
    """
    This class gives us the ability to talk to S3
    using the same connectivity options as bootstrap-cfn

    This means we can connect cross-account by creating an aws
    profile called cross-account and passing an environment
    variable called AWS_ROLE_ARN_ID
    """

    conn_cfn = None
    aws_region_name = None
    aws_profile_name = None

    def __init__(self, aws_profile_name, aws_region_name='eu-west-1'):
        self.aws_profile_name = aws_profile_name
        self.aws_region_name = aws_region_name

        self.conn_kms = utils.connect_to_aws(boto.kms, self)

    def get_key_id(self, alias):
        """
        Get a list of kms key_ids with the alias supplied

        Args:
            alias(string): The string identifier of the alias to
                search for

        Returns:
            (string): Return the first matching key_id found, None type
                if no key_ids were found
        """
        # Queries are paginated, while the results returned are truncated,
        # and we dont have a key_id, keep getting pages
        limit = 50
        truncated = True
        marker = None
        while truncated:
            alias_response = self.conn_kms.list_aliases(limit, marker)
            key_ids = [a['TargetKeyId'] for a in alias_response['Aliases'] if a['AliasName'] == "alias/{0}".format(alias)]
            if len(key_ids) > 0:
                return key_ids[0]
            # Move the query target to the next page
            truncated = alias_response.get('Truncated', False)
            marker = alias_response.get('NextMarker', None)

        return None

    def create_key(self, alias):
        key_id = self.conn_kms.create_key()['KeyMetadata']['KeyId']
        self.conn_kms.create_alias("alias/{0}".format(alias), key_id)
        return key_id

    def generate_data_key(self, key_id):
        ret = self.conn_kms.generate_data_key(key_id, key_spec="AES_256")['CiphertextBlob']
        return base64.b64encode(ret)

    def decrypt(self, cipher_blob):
        return self.conn_kms.decrypt(cipher_blob)
