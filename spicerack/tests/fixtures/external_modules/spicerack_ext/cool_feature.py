"""Cool feature external module."""


class CoolFeature:
    """An external module class."""

    def __init__(self, feature: str, *, dry_run: bool = True):
        """Instantiate the class."""
        self._feature = feature
        self._dry_run = dry_run

    def __str__(self) -> None:
        """String representation of the instance."""
        return f"{self._feature} is a cool feature!"
