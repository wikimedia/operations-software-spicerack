"""Class API get_runner raise cookbook."""
from spicerack.cookbook import CookbookBase


class GetRunnerRaise(CookbookBase):
    """Class API get_runner raise cookbook."""

    def get_runner(self, args):
        """As required by the parent class."""
        raise RuntimeError("get_runner raise")
