"""Cookbook internal module."""
import argparse
from typing import Optional

from spicerack import Spicerack, cookbook


class CookbookModuleRunnerBase(cookbook.CookbookRunnerBase):
    """Abstract class for the dynamically converted module based Cookbooks to class based."""

    def __init__(self, args: argparse.Namespace, spicerack: Spicerack):
        """Constructor, saves the parameters to be passed to the _run() method."""
        self.args = args
        self.spicerack = spicerack

    def run(self) -> Optional[int]:
        """As required by the parent class."""
        return self._run(self.args, self.spicerack)

    @staticmethod
    def _run(args: argparse.Namespace, spicerack: Spicerack) -> Optional[int]:
        """To be dynamically overwritten with the run() module function."""


class CookbooksModuleInterface:
    """Module interface to be used as type hint for the imported cookbooks that use the module API."""

    __name__ = ""
    """str: the module name."""

    __title__: str = ""
    """str: the cookbook static title."""

    @staticmethod
    def argument_parser() -> argparse.ArgumentParser:
        """Optional module function to define if the cookbook should accept command line arguments."""

    @staticmethod
    def run(args: argparse.Namespace, spicerack: Spicerack) -> Optional[int]:
        """Mandatory module function that every cookbook using this interface must define."""
