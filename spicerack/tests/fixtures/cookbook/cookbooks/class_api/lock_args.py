"""Class API example cookbook with custom lock args."""

import argparse

from spicerack.cookbook import CookbookBase, CookbookRunnerBase, LockArgs


class ExampleCookbook(CookbookBase):
    """Cookbook that overrides the lock arguments."""

    def argument_parser(self):
        """As defined by the parent class."""
        return argparse.ArgumentParser("Argparse")

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    @property
    def lock_args(self):
        """Set the lock dynamically."""
        return LockArgs(suffix="test", concurrency=1, ttl=30)

    def run(self):
        """As required by the parent class."""
