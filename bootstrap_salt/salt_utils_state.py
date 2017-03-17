#!/usr/bin/env python
import argparse
from salt.log.setup import setup_console_logger, setup_logfile_logger

import logging

import salt
import salt.client
import salt.config
import salt.output

# Set up the logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap-salt::salt_utils_state")
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger('boto').setLevel(logging.CRITICAL)


class BootstrapUtilError(Exception):
    def __init__(self, msg):
        super(BootstrapUtilError, self).__init__(msg)


class SaltStateError(BootstrapUtilError):
    pass


class SaltParserError(BootstrapUtilError):
    pass


class SaltUtilsStateWrapper():
    """
    Class to wrap the saltutil state caller. It provides some logging
    and error parsing.
    """
    caller = None

    def __init__(self):
        self.caller = salt.client.Caller()

    def highstate(self):
        """
        Highstate the instance with data from the remote s3 bucket
        """
        self.state("highstate")

    def state(self, state):
        """
        Run a salt state with data from the remote s3 bucket

        Args:
            state(string): the state to run
        Raises:
            SaltParserError: if any minion cannot execute the state
            SaltStateError: if any state execution returns False
        """
        logger.info("state: Running state '{}'...".format(state))

        # Highstate has its own state call
        if state == 'highstate':
            result = self.caller.function('state.highstate')
        else:
            result = self.caller.function('state.sls', state)
        logger.debug("state: State results: {}".format(result))
        return self.check_state_result(result)

    def check_state_result(self, result):
        """
        Takes a salt results dictionary, prints the output
        in salts highstate output format and checks all states
        executed successfully. Returns True on success.

        Args:
            result(dict): salt results dictionary

        Raises:
            SaltParserError: if any minion cannot execute the state
            SaltStateError: if any state execution returns False
        """
        __opts__ = salt.config.minion_config('/etc/salt/minion')
        salt.output.display_output({'local': result},
                                   out='highstate',
                                   opts=__opts__)
        if isinstance(result, dict):
            # This uses a syntax parsing check to verify true results
            results = [v['result'] for v in result.values()]
            if all(results):
                logging.info("check_state_result: All states successful")
                return True
            else:
                raise SaltStateError('State did not execute successfully')
        elif isinstance(result, list):
                for entry in result:
                    if "failed" in entry.lower() or "error" in entry.lower():
                        logging.critical("check_state_result: "
                                         "State failed, '{}'"
                                         .format(entry))
                        raise SaltStateError(
                            'State did not execute successfully'
                        )
                return True
        else:
            raise SaltParserError('Minion could not parse state data')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run salt states')
    parser.add_argument('-s',
                        dest='state',
                        type=str,
                        help='Name of state or highstate',
                        required=True)
    parser.add_argument('--loglevel',
                        dest='loglevel',
                        type=str,
                        help=("Level of logging detail, "
                              "debug, info, warning, error or critical"),
                        default="info")
    args = parser.parse_args()
    setup_console_logger(log_level=args.loglevel)
    setup_logfile_logger(log_path='/var/log/salt/minion',
                         log_level=args.loglevel)

    salt_utils_state_wrapper = SaltUtilsStateWrapper()
    salt_utils_state_wrapper.state(args.state)
