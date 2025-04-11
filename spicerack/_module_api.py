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
    """The module name."""

    __title__: str = ""
    """The cookbook static title. If not set the first line of the module docstring will be used."""

    __owner_team__: str = "unowned"
    """Name of the team owning this cookbook and responsible to keep it up to date."""

    MAX_CONCURRENCY: int = CookbookModuleRunnerBase.max_concurrency
    """How many parallel runs of a specific cookbook inheriting from this class are accepted."""

    LOCK_TTL: int = CookbookModuleRunnerBase.lock_ttl
    """The concurrency lock time to live (TTL) in seconds. For each concurrent run a lock is acquired for this amount
    of seconds."""

    @staticmethod
    def argument_parser() -> argparse.ArgumentParser:  # type: ignore[empty-body]
        """Optional module function to define if the cookbook should accept command line arguments."""

    @staticmethod
    def run(args: argparse.Namespace, spicerack: Spicerack) -> Optional[int]:
        """Mandatory module function that every cookbook using this interface must define."""
