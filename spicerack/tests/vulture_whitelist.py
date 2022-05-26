"""Vulture whitelist to avoid false positives."""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _):
        """Mocking magic method __getattr__."""
        pass


whitelist_logging = Whitelist()
whitelist_logging.raiseExceptions

whitelist_ganeti = Whitelist()
whitelist_ganeti.Ganeti._http_session.auth

# Needed because of https://github.com/jendrikseipp/vulture/issues/264
whitelist_dhcp = Whitelist()
whitelist_dhcp.DHCPConfOpt82.ipv4
whitelist_dhcp.DHCPConfOpt82.switch_hostname
whitelist_dhcp.DHCPConfOpt82.switch_iface
whitelist_dhcp.DHCPConfOpt82.vlan
whitelist_dhcp.DHCPConfOpt82.distro
whitelist_dhcp.DHCPConfOpt82.media_type
whitelist_dhcp.DHCPConfMac.ipv4
whitelist_dhcp.DHCPConfMac.mac
whitelist_dhcp.DHCPConfMac.distro
whitelist_dhcp.DHCPConfMac.media_type
whitelist_dhcp.DHCPConfMgmt.lserial
whitelist_dhcp.DHCPConfMgmt.ipv4

whitelist_dnsdisc = Whitelist()
whitelist_dnsdisc.pool
whitelist_dnsdisc.depool

whitelist_icinga = Whitelist()
whitelist_icinga.CommandFile.__new__

whitelist_mysql = Whitelist()
whitelist_mysql.set_core_masters_readonly
whitelist_mysql.set_core_masters_readwrite

whitelist_redfish = Whitelist()
whitelist_redfish.ChassisResetPolicy.FORCE_RESTART
whitelist_redfish.ChassisResetPolicy.GRACEFUL_RESTART
whitelist_redfish.ChassisResetPolicy.GRACEFUL_SHUTDOWN
whitelist_redfish.ChassisResetPolicy.ON
whitelist_redfish.DellSCPRebootPolicy.FORCED
whitelist_redfish.DellSCPRebootPolicy.GRACEFUL
whitelist_redfish.DellSCPPowerStatePolicy.OFF
whitelist_redfish.DellSCPTargetPolicy.BIOS
whitelist_redfish.DellSCPTargetPolicy.IDRAC
whitelist_redfish.DellSCPTargetPolicy.NIC
whitelist_redfish.DellSCPTargetPolicy.RAID
whitelist_redfish.DellSCP.model
whitelist_redfish.DellSCP.comments

whitelist_remote = Whitelist()
whitelist_remote.execute.worker.commands
whitelist_remote.execute.worker.commands
whitelist_remote.execute.worker.handler
whitelist_remote.execute.worker.success_threshold
whitelist_remote.execute.worker.progress_bars
whitelist_remote.execute.worker.reporter
whitelist_remote.run_async
whitelist_remote.run_sync

# Needed because of https://github.com/jendrikseipp/vulture/issues/264
whitelist_service = Whitelist()
whitelist_service.Service.aliases
whitelist_service.Service.bgp
whitelist_service.Service.depool_threshold
whitelist_service.Service.encryption
whitelist_service.Service.lvs
whitelist_service.Service.lvs_class
whitelist_service.Service.monitors
whitelist_service.Service.name
whitelist_service.Service.page
whitelist_service.Service.probes
whitelist_service.Service.protocol
whitelist_service.Service.public_aliases
whitelist_service.Service.public_endpoint
whitelist_service.Service.scheduler
whitelist_service.ServiceMonitoring.check_command
whitelist_service.ServiceMonitoring.contact_group
whitelist_service.ServiceMonitoring.notes_url

whitelist_tests = Whitelist()
whitelist_tests.unit.test_confctl.TestConfctl.setup_method
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.backend
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.config
whitelist_tests.unit.test_elasticsearch_cluster.pytestmark
whitelist_tests.unit.test_netbox._netbox_host
whitelist_tests.unit.test_netbox._netbox_virtual_machine
whitelist_tests.unit.test_remote.TestRemote.setup_method
whitelist_tests.unit.test_remote.TestRemote.teardown_method
