"""Class API runtime_description raise cookbook."""
from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class RuntimeDescriptionRaise(CookbookBase):
    """Class API runtime_description raise cookbook."""

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    @property
    def runtime_description(self):
        """As defined by the parent class."""
        raise RuntimeError("Runtime description raise")

    def run(self):
        """As required by the parent class."""
