"""Top level cookbook"""
import argparse


def get_title(args):
    """Calculate the title based on the args."""
    return '{doc}: {args}'.format(doc=__doc__, args=args)


def argument_parser():
    """As required by spicerack.cookbook."""
    return argparse.ArgumentParser('Argparse')


def run(args, _):
    """As required by spicerack.cookbook."""
    print(args)
    return 0
