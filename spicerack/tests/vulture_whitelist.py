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

whitelist_dnsdisc = Whitelist()
whitelist_dnsdisc.pool
whitelist_dnsdisc.depool

whitelist_mysql = Whitelist()
whitelist_mysql.set_core_masters_readonly
whitelist_mysql.set_core_masters_readwrite

whitelist_remote = Whitelist()
whitelist_remote.execute.worker.commands
whitelist_remote.execute.worker.commands
whitelist_remote.execute.worker.handler
whitelist_remote.execute.worker.success_threshold
whitelist_remote.run_async
whitelist_remote.run_sync

whitelist_tests = Whitelist()
whitelist_tests.unit.test_confctl.TestConfctl.setup_method
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.backend
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.config
whitelist_tests.unit.test_elasticsearch_cluster.pytestmark
whitelist_tests.unit.test_remote.TestRemote.setup_method
whitelist_tests.unit.test_remote.TestRemote.teardown_method
