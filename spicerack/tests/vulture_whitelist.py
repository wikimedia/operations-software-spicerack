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

whitelist_ganeti = Whitelist()
whitelist_ganeti.Ganeti._http_session.auth

# Needed because of https://github.com/jendrikseipp/vulture/issues/264
whitelist_dhcp = Whitelist()
whitelist_dhcp.DHCPConfOpt82.switch_hostname
whitelist_dhcp.DHCPConfOpt82.switch_iface
whitelist_dhcp.DHCPConfOpt82.vlan
whitelist_dhcp.DHCPConfMgmt.serial
whitelist_dhcp.DHCPConfMgmt.ip_address

whitelist_dnsdisc = Whitelist()
whitelist_dnsdisc.pool
whitelist_dnsdisc.depool

whitelist_icinga = Whitelist()
whitelist_icinga.CommandFile.__new__

whitelist_mysql = Whitelist()
whitelist_mysql.set_core_masters_readonly
whitelist_mysql.set_core_masters_readwrite

whitelist_remote = Whitelist()
whitelist_remote.execute.worker.commands
whitelist_remote.execute.worker.commands
whitelist_remote.execute.worker.handler
whitelist_remote.execute.worker.success_threshold
whitelist_remote.execute.worker.progress_bars
whitelist_remote.execute.worker.reporter
whitelist_remote.run_async
whitelist_remote.run_sync

whitelist_tests = Whitelist()
whitelist_tests.unit.test_confctl.TestConfctl.setup_method
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.backend
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.config
whitelist_tests.unit.test_elasticsearch_cluster.pytestmark
whitelist_tests.unit.test_netbox._netbox_host
whitelist_tests.unit.test_netbox._netbox_virtual_machine
whitelist_tests.unit.test_remote.TestRemote.setup_method
whitelist_tests.unit.test_remote.TestRemote.teardown_method
