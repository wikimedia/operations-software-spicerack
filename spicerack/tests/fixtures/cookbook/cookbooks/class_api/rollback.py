"""Class API rollback cookbook."""
import argparse
import logging

from spicerack.cookbook import CookbookBase, CookbookRunnerBase

logger = logging.getLogger()


class RollbackCookbook(CookbookBase):
    """Class API rollback cookbook."""

    def argument_parser(self):
        """As defined by the parent class."""
        return argparse.ArgumentParser("Argparse")

    def get_runner(self, args):
        """As required by the parent class."""
        return RollbackRunner()


class RollbackRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    def run(self):
        """As required by the parent class."""
        raise RuntimeError("run has raised")

    def rollback(self):
        """Define rollback actions."""
        logger.error("rollback called")
