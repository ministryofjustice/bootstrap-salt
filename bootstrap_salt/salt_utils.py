#!/usr/bin/env python
import argparse
import logging
import sys
import subprocess

# Set up the logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap-salt::salt_utils")
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger('boto').setLevel(logging.CRITICAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=('Update the salt config '
                     'from a remote s3 store and run a salt state')
    )
    parser.add_argument('-s',
                        dest='state',
                        type=str,
                        help='Name of state or highstate'
                        )
    parser.add_argument('--disable-update',
                        dest='disable_update',
                        help=('Disable the updating of salt config data '
                              'from the remote repository.'),
                        action='store_true'
                        )
    parser.add_argument('--ignore-errors',
                        dest='ignore_errors',
                        help=('Ignore problems and continue execution.'),
                        action='store_true'
                        )
    parser.add_argument('--update-only',
                        dest='update_only',
                        help=('Do not run a state, only update the config '
                              'data from the remote.'),
                        action='store_true'
                        )
    parser.add_argument('--loglevel',
                        dest='loglevel',
                        type=str,
                        help=('Level of logging detail, '
                              'debug, info, warning, error or critical'),
                        default="info")
    args = parser.parse_args()
    logger.debug("Running with arg {}"
                 .format(args))
    # Catch inconsistent arg combinations
    if args.state is None and not args.update_only:
        logger.critical("Theres not state argument and update_only is not set, "
                        "please specify a state to run or only to update the data"
                        "... aborting")
        sys.exit(1)
    if args.state and args.update_only:
        logger.critical("The state and update_only arguments are mutually "
                        "exclusive, please choose only one at a time... aborting")
        sys.exit(1)
    if not args.update_only and args.state is None:
        logger.critical("The state argument is required unless the update_only "
                        " argument is set... aborting")
        sys.exit(1)

    if not args.disable_update:
        # Sync the salt data from an the s3 store and synchronise
        return_code = subprocess.call(["salt_utils_update.py",
                                       "--loglevel",
                                       args.loglevel])
        if return_code != 0:
            if not args.ignore_errors:
                logger.critical("There was a problem updating the "
                                "remote salt data...aborting.")
                sys.exit(return_code)
            else:
                logger.critical("There was a problem updating the remote salt data, "
                                "ignore errors set so continuing execution.")

    if not args.update_only:
        # Run the state
        return_code = subprocess.call(["salt_utils_state.py",
                                       "-s",
                                       args.state,
                                       "--loglevel",
                                       args.loglevel])
        if return_code != 0:
            if not args.ignore_errors:
                logger.critical("There was a problem running the "
                                "salt state...aborting.")
                sys.exit(return_code)
            else:
                logger.critical("There was a problem running the salt state,"
                                "ignore errors set so continuing execution.")
    sys.exit(0)
