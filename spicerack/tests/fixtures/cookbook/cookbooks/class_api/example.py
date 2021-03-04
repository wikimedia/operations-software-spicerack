"""Class API example cookbook."""
import argparse

from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class ExampleCookbook(CookbookBase):  # noqa: D101
    # No docstring to test the spicerack.cookbook.CookbookBase.title implementation

    def argument_parser(self):
        """As defined by the parent class."""
        return argparse.ArgumentParser("Argparse")

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    def run(self):
        """As required by the parent class."""
