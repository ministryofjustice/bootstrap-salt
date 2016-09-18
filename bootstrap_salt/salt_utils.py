#!/usr/bin/env python
import argparse
import subprocess

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=('Update the salt config '
                     'from a remote s3 store and run a salt state')
    )
    parser.add_argument('-s',
                        dest='state',
                        type=str,
                        help='Name of state or highstate',
                        required=True)
    parser.add_argument('--loglevel',
                        dest='loglevel',
                        type=str,
                        help=('Level of logging detail, '
                              'debug, info, warning, error or critical'),
                        default="info")
    args = parser.parse_args()
    # Sync the salt data from an the s3 store and synchronise
    subprocess.call(["salt_utils_update.py",
                     "--loglevel",
                     args.loglevel])
    # Run the state
    subprocess.call(["salt_utils_state.py",
                     "-s",
                     args.state,
                     "--loglevel",
                     args.loglevel])
