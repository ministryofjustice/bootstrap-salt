import errno
import os
import shutil
import time

import boto.exception
import boto.provider
import boto.sts

from bootstrap_salt import errors


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
    except boto.provider.ProfileNotFoundError:
        raise errors.ProfileNotFoundError(instance.aws_profile_name)


def copytree(src, dst, symlinks=False, ignore=None):
    """
    Behave exaclty like copytree from shutil standard library but don't
    complain when the target directory already exists.

    This version was taken from python 2.7.8_2 on OSX and the only changes are
    the `try`/`except` around the `os.makedirs` call. Annoyingly copying the
    function wholesale seems to be the only solution to this problem.
    """

    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    try:
        os.makedirs(dst)
    except OSError, e:
        # If the directory already eixsts then carry on.
        if e.errno == errno.EEXIST:
            pass
        else:
            raise

    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks, ignore)
            else:
                # Will raise a SpecialFileError for unsupported file types
                shutil.copy2(srcname, dstname)
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except shutil.Error, err:
            errors.extend(err.args[0])
        except EnvironmentError, why:
            errors.append((srcname, dstname, str(why)))
    try:
        shutil.copystat(src, dst)
    except OSError, why:
        if WindowsError is not None and isinstance(why, WindowsError):
            # Copying file access times may fail on Windows
            pass
        else:
            errors.append((src, dst, str(why)))
    if errors:
        raise shutil.Error, errors
