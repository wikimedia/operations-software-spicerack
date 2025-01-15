"""Cookbook that uses extended accessors from external modules."""

import sys

from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class ExternalModulesCookbook(CookbookBase):
    """Call a Spicerack extender accessor."""

    def get_runner(self, _):
        """As required by the parent class."""
        return ExternalModulesRunner(self.spicerack)


class ExternalModulesRunner(CookbookRunnerBase):
    """The cookbook runner."""

    def __init__(self, spicerack):
        """Initialize the instance."""
        self.spicerack = spicerack

    def run(self):
        """As required by the parent class."""
        print(self.spicerack.cool_feature("Extender"), file=sys.stderr)
