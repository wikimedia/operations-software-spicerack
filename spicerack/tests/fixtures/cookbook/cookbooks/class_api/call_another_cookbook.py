"""Call another cookbook cookbook."""

import argparse

from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class CallAnotherCookbook(CookbookBase):
    """A cookbook that calls another cookbook."""

    owner_team = "team1"

    def argument_parser(self):
        """As defined by the parent class."""
        parser = argparse.ArgumentParser("Argparse")
        parser.add_argument("cookbook", help="The path of the cookbook to execute.")
        parser.add_argument("--raises", action="store_true", help="Set raises=True in run_cookbook")
        parser.add_argument("--confirm", action="store_true", help="Set confirm=True in run_cookbook")
        return parser

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner(args, self.spicerack)


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    def __init__(self, args, spicerack):
        """Initialize the instance."""
        self.args = args
        self.spicerack = spicerack

    def run(self):
        """As required by the parent class."""
        return self.spicerack.run_cookbook(self.args.cookbook, [], raises=self.args.raises, confirm=self.args.confirm)
