#!/usr/bin/env python

import redis
import os
import sys
import yaml


def connect_to_redis():
    """
    Connect to a Redis server
    REDIS_* are defined in jenkins configure as environment variables.

    Return:
        (redis object): return connected redis object
    """
    try:
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = os.environ.get("REDIS_PORT", 16379)
        redis_db = os.environ.get("REDIS_DB", 0)
    except KeyError as e:
        print("Read Redis environment variables error: %s" % e,
              sys.stderr)
        sys.exit(1)
    try:
        redis_server = redis.StrictRedis(redis_host, redis_port, redis_db)
    except (redis.exceptions.ConnectionError,
            redis.exceptions.BusyLoadingError) as e:
        print("Redis connection error: %s" % e, sys.stderr)
        sys.exit(1)
    return redis_server


def get_github_users():
    """
    Return github user list in MoJ from pillar/keys.sls
    """
    pillar_file = "/srv/pillar/keys.sls"
    ssh_user_data = set()
    if os.path.exists(pillar_file):
        with open(pillar_file) as key_config:
            user_data = yaml.load(key_config)
            key_config = user_data.get('admins', {})
            ssh_user_data = key_config.keys()
    else:
        print("Error: %s does not exist." % pillar_file,
              sys.stderr)
        sys.exit(1)
    return ssh_user_data


def get_current_users():
    """
    Return authorized ssh user list filtered from /etc/passwd
    """
    users_file = '/etc/passwd'
    if os.path.exists(users_file):
        os.system("cat /etc/passwd | grep 'bin/bash' | grep '[1-9][0-9][0-9][0-9]:'| cut -d ':' -f1 > ./current_users")
        with open("current_users") as current_user_file:
            current_users_list = [user.strip() for user in current_user_file]
    else:
        current_users_list = []
    return current_users_list


def check_users(github_users_list, current_users_list):
    """
    If the user is not on github user list, push its info to elk.
    Args:
        github_users_list: gtihub user list generated from pillar/keys.sls
        current_users_list: current authorized users from /etc/passwd
    """
    redis_server = connect_to_redis()
    for to_be_moved in current_users_list:
        if to_be_moved not in github_users_list:
            message = {"user": to_be_moved.strip("\n"), "absent": True}
            try:
                redis_server.rpush("logstash:sshusercheck", message)
            except (redis.exceptions.ConnectionError,
                    redis.exceptions.BusyLoadingError) as e:
                print("Redis connection error: %s" % e, sys.stderr)
                sys.exit(1)


def main():
    check_users(get_github_users(), get_current_users())


if __name__ == '__main__':
    main()
