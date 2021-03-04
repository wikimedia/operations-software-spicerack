"""Class API cookbook that overrides runtime_description."""
from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class RuntimeDescription(CookbookBase):
    """Class API cookbook that overrides runtime_description."""

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    @property
    def runtime_description(self):
        """As defined by the parent class."""
        return "Runtime description"

    def run(self):
        """As required by the parent class."""
