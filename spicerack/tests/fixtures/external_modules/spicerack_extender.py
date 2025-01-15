"""Spicerack extender for the external modules."""

from spicerack_ext.cool_feature import CoolFeature

from spicerack import SpicerackExtenderBase


class SpicerackExtender(SpicerackExtenderBase):
    """Spicerack extender to add custom accessors."""

    def cool_feature(self, feature: str) -> CoolFeature:
        """Get a CoolFeature instance.

        Arguments:
            feature: the feature to make cool.

        Returns:
            spicerack_ext.cool_feature.CoolFeature: the cool feature instance.

        """
        return CoolFeature(feature, dry_run=self._spicerack.dry_run)


class SpicerackBadExtender:
    """An extender that doesn't inherit from SpicerackExtenderBase."""
