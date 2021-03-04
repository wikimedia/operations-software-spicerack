"""Group2 Cookbook2.

Multiline doc that will be cut to one-line in the __title__.
"""
import argparse

__title__ = __doc__


def argument_parser():
    """As required by spicerack._cookbook."""
    parser = argparse.ArgumentParser("Argparse")
    parser.add_argument("-k", action="store_true")
    parser.add_argument("--argument")

    return parser


def run(args, spicerack):
    """As required by spicerack._cookbook."""
    print([dict(sorted(vars(args).items())), spicerack.verbose, spicerack.dry_run])
    return 0
