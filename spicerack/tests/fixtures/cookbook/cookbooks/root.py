"""Top level cookbook."""
import argparse

__title__ = __doc__


def argument_parser():
    """As required by spicerack._cookbook."""
    return argparse.ArgumentParser("Argparse")


def run(args, _):
    """As required by spicerack._cookbook."""
    print(args)
    return 0
