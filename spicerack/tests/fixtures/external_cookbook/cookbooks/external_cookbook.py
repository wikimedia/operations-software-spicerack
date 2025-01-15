"""Top level class external cookbook."""

from spicerack.cookbook import CookbookBase, CookbookRunnerBase


class ExampleCookbook(CookbookBase):
    """Top level class external cookbook."""

    def get_runner(self, args):
        """As required by the parent class."""
        return ExampleRunner()


class ExampleRunner(CookbookRunnerBase):
    """As required by spicerack._cookbook."""

    def run(self):
        """As required by the parent class."""
