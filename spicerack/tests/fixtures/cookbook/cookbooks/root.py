"""Top level cookbook."""
import argparse


__title__ = __doc__


def argument_parser():
    """As required by spicerack.cookbook."""
    return argparse.ArgumentParser('Argparse')


def run(args, _):
    """As required by spicerack.cookbook."""
    print(args)
    return 0
