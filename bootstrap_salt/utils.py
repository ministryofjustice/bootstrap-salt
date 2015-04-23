import boto.exception
import boto.provider
import boto.sts
import time
import os

import errors


def timeout(timeout, interval):
    def decorate(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while True:
                result = func(*args, **kwargs)
                if result:
                    return result
                if attempts >= timeout / interval:
                    raise errors.CfnTimeoutError("Timeout in {0}".format(func.__name__))
                attempts += 1
                time.sleep(interval)
        return wrapper
    return decorate


def connect_to_aws(module, instance):
    try:
        if instance.aws_profile_name == 'cross-account':
            sts = boto.sts.connect_to_region(
                region_name=instance.aws_region_name,
                profile_name=instance.aws_profile_name
            )
            role = sts.assume_role(
                role_arn=os.environ['AWS_ROLE_ARN_ID'],
                role_session_name="AssumeRoleSession1"
            )
            conn = module.connect_to_region(
                region_name=instance.aws_region_name,
                aws_access_key_id=role.credentials.access_key,
                aws_secret_access_key=role.credentials.secret_key,
                security_token=role.credentials.session_token
            )
            return conn
        conn = module.connect_to_region(
            region_name=instance.aws_region_name,
            profile_name=instance.aws_profile_name
        )
        return conn
    except boto.exception.NoAuthHandlerFound:
        raise errors.NoCredentialsError()
    except boto.provider.ProfileNotFoundError as e:
        raise errors.ProfileNotFoundError(instance.aws_profile_name)
