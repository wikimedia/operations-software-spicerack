"""Class API rollback_raise cookbook."""
import argparse

from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class RollbackRaiseCookbook(CookbookBase):
    """Class API rollback_raise cookbook."""

    def argument_parser(self):
        """As defined by the parent class."""
        return argparse.ArgumentParser("Argparse")

    def get_runner(self, args):
        """As required by the parent class."""
        return RollbackRaiseRunner()


class RollbackRaiseRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    def run(self):
        """As required by the parent class."""
        return 1

    def rollback(self):
        """Rollback raises."""
        raise RuntimeError("rollback has raised")
