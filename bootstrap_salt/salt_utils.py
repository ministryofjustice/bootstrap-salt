#!/usr/bin/env python
import salt
import salt.runner
import salt.config
import salt.client
import salt.output
import time
import sys
import math


class BootstrapUtilError(Exception):

    def __init__(self, msg):
        print >> sys.stderr, "[ERROR] {0}: {1}".format(self.__class__.__name__, msg)


class SaltStateError(BootstrapUtilError):
    pass


class SaltParserError(BootstrapUtilError):
    pass


class UtilTimeoutError(BootstrapUtilError):
    pass


def do_nothing(*args, **kwargs):
    pass


def get_minions_batch(target, fraction=None):
    '''
    Takes a salt glob target and returns batches of minion ids that match
    in the format [['minion1','minion2']]
    If a fraction is specified the minions are split into batches sized by
    that fraction i.e. 4 minions with fraction=0.5 will return:
    [['minion1', 'minion2'],['minion3','minion4']]
    '''
    local = salt.client.LocalClient()
    minions = local.cmd(target, 'test.ping').keys()
    if fraction:
        number_in_batch = int(math.ceil(len(minions)*float(fraction)))
        return [minions[i:i+number_in_batch] for i in xrange(0, len(minions), number_in_batch)]
    else:
        return [minions]


def do_timeout(timeout, interval):

    def decorate(func):

        def wrapper(*args, **kwargs):
            attempts = 0
            while True:
                result = func(*args, **kwargs)
                if result:
                    return result
                if attempts >= timeout / interval:
                    raise UtilTimeoutError("Timeout in {0}".format(func.__name__))
                attempts += 1
                time.sleep(interval)
        return wrapper
    return decorate


def start_highstate(target, expr_form='list'):
    local = salt.client.LocalClient()
    jid = local.cmd_async(target, 'state.highstate', expr_form=expr_form)
    return jid


def start_state(target, state, expr_form='list'):
    local = salt.client.LocalClient()
    jid = local.cmd_async(target, 'state.sls', [state], expr_form=expr_form)
    return jid


def state_result(jid):
    opts = salt.config.master_config('/etc/salt/master')
    # This is added because salt 2014.7 no longer prints all the output from
    # a highstate when you lookup the jid. Instead we print the output ourselves
    # when we check the result and overwrite the salt outputter here to do
    # nothing.
    d_o = salt.output.display_output
    salt.output.display_output = do_nothing
    r = salt.runner.RunnerClient(opts)
    result = r.cmd('jobs.lookup_jid', [jid])
    salt.output.display_output = d_o
    if result:
        return result
    return False


def highstate(target, fraction, timeout, interval):
    results = []
    for b in get_minions_batch(target, fraction):
        jid = start_highstate(','.join(b), expr_form='list')
        res = do_timeout(timeout, interval)(state_result)(jid)
        results.append(check_state_result(res))
        print "Minions {0} complete".format(b)
    return all(results)


def state(target, state, fraction, timeout, interval):
    results = []
    for b in get_minions_batch(target, fraction):
        jid = start_state(','.join(b), state, expr_form='list')
        res = do_timeout(timeout, interval)(state_result)(jid)
        results.append(check_state_result(res))
        print "Minions {0} complete".format(b)
    return all(results)


def check_state_result(result):
    results = []
    __opts__ = salt.config.master_config('/etc/salt/master')
    for minion, ret in result.items():
        salt.output.display_output({minion: ret}, out='highstate', opts=__opts__)
        if isinstance(ret, dict):
            results += [v['result'] for v in ret.values()]
        else:
            raise SaltParserError('Minion could not parse state data')
    if all(results):
        return True
    else:
        raise SaltStateError('State did not execute successfully')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Run salt states')
    parser.add_argument('-t', dest='target', type=str,
                        help='target', required=True)
    parser.add_argument('-f', dest='fraction', type=float,
                        help='for zero downtime deploy, decimal fraction of'
                        'minions to deploy to at one time.', required=False,
                        default=None)
    parser.add_argument('-s', dest='state', type=str,
                        help='Name of state or "highstate"', required=True)
    parser.add_argument('-T', dest='timeout', type=float,
                        help='Timeout to wait for state execution to finish'
                        'on all minions.', required=False, default=1800)
    parser.add_argument('-I', dest='interval', type=float,
                        help='Interval to check for finished execution.',
                        required=False, default=10)

    args = parser.parse_args()
    if args.state == "highstate":
        highstate(args.target, args.fraction, args.timeout, args.interval)
    else:
        state(args.target, args.state, args.fraction, args.timeout, args.interval)
