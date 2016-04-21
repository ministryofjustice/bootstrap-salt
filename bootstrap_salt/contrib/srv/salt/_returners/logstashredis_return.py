# -*- coding: utf-8 -*-
# Import python libs
import json
import logging
import sys

# Import third party libs
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

'''
Return data to a redis server

To enable this returner the minion will need the python client for redis
installed and the following values configured in the minion or master
config, these are the defaults:

    redis.db: '0'
    redis.host: 'salt'
    redis.port: 6379

  To use the redis returner, append '--return logstashredis' to the salt command. ex:

    salt '*' test.ping --return logstashredis

Since bootstrap-salt is an opinionated layer, we've made the following
modifications in order to make it for purpose:

1. the name of the list where the results are prepended is
configurable from the beaver.redis.namespace pillar

2. The results along with the minion id, jid, and the actual results
are wrapped around in a logstash compatible message

3. All functionality relating to the external job cache have been
removed as they are not needed by the core returner functionality in
current Salt version
'''

'''
This file started as a copy of the redis_returner.py file present
in all recent versions of Saltstack.
'''


# Define the module's virtual name
__virtualname__ = 'logstashredis'

# Create a logger
log = logging.getLogger(__name__)


def __virtual__():
    if not HAS_REDIS:
        return False
    return __virtualname__


def _get_serv():
    '''
    Return a redis server object
    '''
    host = get_salt_config_option("redis.host")
    port = get_salt_config_option("redis.port")
    db = get_salt_config_option("redis.db")
    return redis.Redis(
        host, port, db,
        socket_timeout=5)


def get_pillar(pillar):
    try:
        log.info("Getting pillar {0}".format(pillar))
        val = __salt__['pillar.get'](pillar)  # NOQA
        log.info("grain {0}:{1}".format(pillar, val))
    except:
        log.info("Failure to get pillar {0}.".format(pillar))
        val = None

    return val


def get_salt_config_option(option):
    try:
        log.info("Getting config option {0}".format(option))
        optval = __salt__['config.option'](option)  # NOQA
        log.info("option: {0}:{1}".format(option, optval))
    except:
        log.info("Failure to get config option {0}".format(option))
        optval = None

    return optval


def returner(ret):
    '''
    Return data to a redis data store
    '''
    serv = _get_serv()

    try:
        pillar = get_pillar('beaver:redis:namespace')
        print "push {0}".format(pillar)
        serv.rpush("{0}".format(pillar), json.dumps(ret))
    except:
        log.debug(sys.exc_info())
        raise
