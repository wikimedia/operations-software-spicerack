"""Run something and abort successfully in init."""

import argparse

from spicerack.cookbook import CookbookBase, CookbookInitSuccess, CookbookRunnerBase


class AbortInitCookbook(CookbookBase):
    """A cookbook that aborts successfully in its runner's init."""

    owner_team = "team1"

    def argument_parser(self):
        """As defined by the parent class."""
        parser = argparse.ArgumentParser("Argparse")
        parser.add_argument("--message", help="A message to log.")
        return parser

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner(args, self.spicerack)


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack API."""

    def __init__(self, args, _spicerack):
        """Initialize the instance."""
        if args.message:
            raise CookbookInitSuccess(args.message)
        raise CookbookInitSuccess()

    def run(self):
        """As required by the parent class."""
        raise RuntimeError()  # This should never be executed
