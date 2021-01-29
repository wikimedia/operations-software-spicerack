"""Group3 argument_parser() raise SystemExit."""
import argparse

__title__ = __doc__


def argument_parser():
    """As required by spicerack._cookbook."""
    parser = argparse.ArgumentParser("group3.argument_parser_raise_system_exit")
    parser.add_argument("required")
    return parser


def run(_args, _spicerack):
    """As required by spicerack._cookbook."""
