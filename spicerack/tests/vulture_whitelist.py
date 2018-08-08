"""Vulture whitelist to avoid false positives."""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _):
        """Mocking magic method __getattr__."""
        pass


whitelist_logging = Whitelist()
whitelist_logging.raiseExceptions

# Needed for vulture < 0.27
whitelist_mock = Whitelist()
whitelist_mock.return_value
whitelist_mock.side_effect

whitelist_log = Whitelist()
whitelist_log.IRCSocketHandler.level

whitelist_tests = Whitelist()
whitelist_tests.unit.test_confctl.TestConfctl.setup_method
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.backend
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.config
