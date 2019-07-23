"""Group2 Cookbook2."""
import argparse


__title__ = __doc__


def argument_parser():
    """As required by spicerack.cookbook."""
    parser = argparse.ArgumentParser('Argparse')
    parser.add_argument('-k', action='store_true')
    parser.add_argument('--argument')

    return parser


def run(args, spicerack):
    """As required by spicerack.cookbook."""
    print([args, spicerack.verbose, spicerack.dry_run])
    return 0
