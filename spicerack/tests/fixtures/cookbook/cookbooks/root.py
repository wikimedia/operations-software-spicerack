"""Top level cookbook."""

import argparse

__title__ = __doc__
MAX_CONCURRENCY = 5
LOCK_TTL = 120


def argument_parser():
    """As required by spicerack._cookbook."""
    return argparse.ArgumentParser("Argparse")


def run(args, _):
    """As required by spicerack._cookbook."""
    print(args)
    return 0
