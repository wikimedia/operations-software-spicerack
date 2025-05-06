"""Vulture whitelist to avoid false positives."""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _):
        """Mocking magic method __getattr__."""
        pass


whitelist__menu = Whitelist()
whitelist__menu.CookbookItem._parse_args.parser.prog
whitelist__menu.CookbookItem._parse_args.parser.epilog

# Needed because of https://github.com/jendrikseipp/vulture/issues/264
whitelist_dhcp = Whitelist()
whitelist_dhcp.DHCPConfOpt82.ipv4
whitelist_dhcp.DHCPConfOpt82.switch_hostname
whitelist_dhcp.DHCPConfOpt82.switch_iface
whitelist_dhcp.DHCPConfOpt82.vlan
whitelist_dhcp.DHCPConfOpt82.rendered_dhcp_options
whitelist_dhcp.DHCPConfOpt82.rendered_dhcp_filename
whitelist_dhcp.DHCPConfMac.ipv4
whitelist_dhcp.DHCPConfMac.rendered_dhcp_options
whitelist_dhcp.DHCPConfMac.rendered_dhcp_filename
whitelist_dhcp.DHCPConfMgmt.ipv4

whitelist_icinga = Whitelist()
whitelist_icinga.CommandFile.__new__
whitelist_icinga.IcingaStatus.CRITICAL
whitelist_icinga.IcingaStatus.UNKNOWN

whitelist_redfish = Whitelist()
whitelist_redfish.ChassisResetPolicy.FORCE_RESTART
whitelist_redfish.ChassisResetPolicy.GRACEFUL_RESTART
whitelist_redfish.ChassisResetPolicy.GRACEFUL_SHUTDOWN
whitelist_redfish.DellSCPRebootPolicy.FORCED
whitelist_redfish.DellSCPRebootPolicy.GRACEFUL
whitelist_redfish.DellSCPPowerStatePolicy.OFF
whitelist_redfish.DellSCPTargetPolicy.BIOS
whitelist_redfish.DellSCPTargetPolicy.IDRAC
whitelist_redfish.DellSCPTargetPolicy.NIC
whitelist_redfish.DellSCPTargetPolicy.RAID
whitelist_redfish.DellSCP.comments

whitelist_remote = Whitelist()
whitelist_remote.execute.worker.progress_bars
whitelist_remote.execute.worker.reporter

# Needed because of https://github.com/jendrikseipp/vulture/issues/264
whitelist_service = Whitelist()
whitelist_service.Service.aliases
whitelist_service.Service.bgp
whitelist_service.Service.depool_threshold
whitelist_service.Service.encryption
whitelist_service.Service.httpbb_dir
whitelist_service.Service.lvs
whitelist_service.Service.lvs_class
whitelist_service.Service.monitors
whitelist_service.Service.page
whitelist_service.Service.probes
whitelist_service.Service.protocol
whitelist_service.Service.public_aliases
whitelist_service.Service.public_endpoint
whitelist_service.Service.scheduler
whitelist_service.Service.scheduler_flag
whitelist_service.Service.ipip_encapsulation
whitelist_service.ServiceMonitoring.check_command
whitelist_service.ServiceMonitoring.contact_group
whitelist_service.ServiceMonitoring.notes_url

whitelist_tests = Whitelist()
whitelist_tests.unit.test_confctl.TestConfctl.setup_method.backend
whitelist_tests.unit.test_dnsdisc.MockDnsResult.canonical_name
whitelist_tests.unit.test_dnsdisc.MockDnsResult.minimum_ttl
whitelist_tests.unit.test_elasticsearch_cluster.pytestmark
whitelist_tests.unit.test_netbox._netbox_host
whitelist_tests.unit.test_netbox._netbox_virtual_machine
