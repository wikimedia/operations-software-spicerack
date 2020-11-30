"""Multiple cookbook classes."""
from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class CookbookA(CookbookBase):
    """Multiple cookbook classes."""

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class CookbookB(CookbookBase):
    """Multiple cookbook classes."""

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    def run(self):
        """As required by the parent class."""
