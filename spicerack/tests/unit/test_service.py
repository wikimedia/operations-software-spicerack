"""Service Module Tests."""
from ipaddress import ip_address
from unittest import mock

import pytest
from wmflib.config import load_yaml_config

from spicerack import service
from spicerack.administrative import Reason
from spicerack.tests import get_fixture_path


def test_service_discovery_no_records():
    """It should raise a DiscoveryRecordNotFoundError exception if no records are present."""
    discovery = service.ServiceDiscovery([])
    with pytest.raises(service.DiscoveryRecordNotFoundError, match="No DNS Discovery record present."):
        discovery.get()


class TestCatalog:
    """Test class for the Catalog class."""

    def setup_method(self):
        """Initialize the tests."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_confctl = mock.MagicMock()
        self.mocked_remote = mock.MagicMock()
        catalog = load_yaml_config(get_fixture_path("service", "service.yaml"))
        self.catalog = service.Catalog(catalog, self.mocked_confctl, self.mocked_remote)

    def test_init(self):
        """It should instantiate a Catalog instance properly."""
        assert isinstance(self.catalog, service.Catalog)

    def test_service_names(self):
        """It should return the list of all service names."""
        assert self.catalog.service_names == ["service1", "service_no_lvs", "service2", "service3"]

    def test_get_instance(self):
        """It should return a Service instance for the given service."""
        assert isinstance(self.catalog.get("service1"), service.Service)

    def test_get_raise(self):
        """It should raise a ServiceNotFoundError if the service is not found."""
        with pytest.raises(service.ServiceNotFoundError, match="Service nonexistent was not found"):
            self.catalog.get("nonexistent")

    def test_iter(self):
        """It should allow to iterate over the catalog and get a Service instance for each service."""
        assert [service.name for service in self.catalog] == self.catalog.service_names

    def test_len(self):
        """It should return the number of services in the catalog."""
        assert len(self.catalog) == 4


class TestService:
    """Test class for the Service class."""

    def setup_method(self):
        """Initialize the tests."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_confctl = mock.MagicMock()
        self.mocked_remote = mock.MagicMock()

        catalog = load_yaml_config(get_fixture_path("service", "service.yaml"))
        self.catalog = service.Catalog(catalog, self.mocked_confctl, self.mocked_remote, dry_run=False)

        self.service1 = self.catalog.get("service1")
        self.service2 = self.catalog.get("service2")
        self.service3 = self.catalog.get("service3")
        self.service_no_lvs = self.catalog.get("service_no_lvs")

    @pytest.mark.parametrize(
        "attrs, obj_type",
        (
            ((), service.Service),
            (("discovery",), service.ServiceDiscovery),
            (("discovery", "get"), service.ServiceDiscoveryRecord),
            (("ip",), service.ServiceIPs),
            (("lvs",), service.ServiceLVS),
            (("lvs", "conftool"), service.ServiceLVSConftool),
            (("monitoring",), service.ServiceMonitoring),
            (("monitoring", "sites"), service.ServiceMonitoringHostnames),
        ),
    )
    def test_instances_service1(self, attrs, obj_type):
        """The service properties should be an instance of the given class."""
        obj = self.service1
        for attr in attrs:
            obj = getattr(obj, attr)
            if callable(obj):
                obj = obj()

        assert isinstance(obj, obj_type)

    @pytest.mark.parametrize(
        "attr, obj_type",
        (
            ("", service.Service),
            ("ip", service.ServiceIPs),
        ),
    )
    def test_instances_service2(self, attr, obj_type):
        """The service properties should be an instance of the given class."""
        obj = self.service2
        if attr:
            obj = getattr(obj, attr)

        assert isinstance(obj, obj_type)

    @pytest.mark.parametrize(
        "attrs, expected",
        (
            (("name",), "service1"),
            (("description",), "Service1 description"),
            (("discovery", "get", "dnsdisc"), "service1"),
            (("discovery", "get", "active_active"), True),
            (("encryption",), True),
            (("ip", "all"), [ip_address("10.2.1.1"), ip_address("10.2.2.1")]),
            (("ip", "sites"), ["codfw", "eqiad"]),
            (("lvs", "depool_threshold"), ".5"),
            (("lvs", "enabled"), True),
            (("lvs", "lvs_class"), "low-traffic"),
            (("lvs", "bgp"), True),
            (("lvs", "protocol"), "tcp"),
            (("lvs", "scheduler"), "wrr"),
            (("lvs", "conftool", "cluster"), "cluster1"),
            (("lvs", "conftool", "service"), "service1"),
            (("monitoring", "check_command"), "check_https_lvs_on_port!service1.discovery.wmnet!443!/health"),
            (("monitoring", "contact_group"), ""),
            (("monitoring", "notes_url"), ""),
            (("monitoring", "sites", "all"), ["service1.svc.codfw.wmnet", "service1.svc.eqiad.wmnet"]),
            (("monitoring", "sites", "sites"), ["codfw", "eqiad"]),
            (("page",), False),
            (("port",), 443),
            (("probes",), [{"type": "http", "path": "/health"}]),
            (("sites",), ["codfw", "eqiad"]),
            (("state",), "production"),
        ),
    )
    def test_property_service1(self, attrs, expected):
        """It should access the Service 1 properties and return their value."""
        obj = self.service1
        for attr in attrs:
            obj = getattr(obj, attr)
            if callable(obj):
                obj = obj()

        assert obj == expected

    @pytest.mark.parametrize(
        "attr, expected",
        (
            ("discovery", None),
            ("lvs", None),
            ("monitoring", None),
            ("page", True),
        ),
    )
    def test_property_service2(self, attr, expected):
        """It should access the Service 2 properties missing and return their default values."""
        assert getattr(self.service2, attr) == expected

    @pytest.mark.parametrize(
        "site, label, expected",
        (
            ("codfw", "", ip_address("10.2.1.1")),
            ("codfw", "default", ip_address("10.2.1.1")),
            ("eqiad", "", ip_address("10.2.2.1")),
            ("nonexistent", "", None),
            ("nonexistent", "nonexistent", None),
        ),
    )
    def test_ip_sites_get(self, site, label, expected):
        """It should return the hostname/FQDN of the given site."""
        if label:
            assert self.service1.ip.get(site, label=label) == expected
        else:
            assert self.service1.ip.get(site) == expected

    @pytest.mark.parametrize(
        "site, expected",
        (
            ("codfw", "service1.svc.codfw.wmnet"),
            ("eqiad", "service1.svc.eqiad.wmnet"),
            ("nonexistent", ""),
        ),
    )
    def test_monitoring_sites_get(self, site, expected):
        """It should return the hostname/FQDN of the given site."""
        assert self.service1.monitoring.sites.get(site) == expected

    def test_discovery_multiple_records(self):
        """It should allow to access all of them."""
        dnsdisc = ["service3_a", "service3_b"]
        active = [True, False]
        discovery = self.service3.discovery
        assert len(discovery) == len(dnsdisc)
        for i, record in enumerate(discovery):
            assert record.dnsdisc == dnsdisc[i]
            assert record.active_active == active[i]
            assert self.service3.discovery.get(record.dnsdisc) is record

    def test_discovery_get_multiple_records_no_name(self):
        """It should raise a TooManyDiscoveryRecordsError exception if name is not passed with multiple records."""
        with pytest.raises(
            service.TooManyDiscoveryRecordsError, match="There are 2 DNS Discovery records but dnsdisc was not set."
        ):
            self.service3.discovery.get()

    def test_discovery_get_multiple_records_not_found(self):
        """It should raise a DiscoveryRecordNotFoundError exception if no matching record is found."""
        with pytest.raises(
            service.DiscoveryRecordNotFoundError, match="Unable to find DNS Discovery record nonexistent."
        ):
            self.service3.discovery.get("nonexistent")

    def test_discovery_get_multiple_records_too_many(self):
        """It should raise a TooManyDiscoveryRecordsError exception if more than one match is found."""
        with pytest.raises(
            service.TooManyDiscoveryRecordsError,
            match="There are 2 DNS Discovery records matching name service_no_lvs.",
        ):
            self.service_no_lvs.discovery.get("service_no_lvs")

    def test_discovery_depool(self):
        """It should depool the correct service from DNS Discovery from the given site."""
        self.service1.discovery.depool("codfw")
        self.mocked_confctl.set_and_verify.assert_called_once_with("pooled", False, dnsdisc="(service1)", name="codfw")
        self.mocked_remote.query.assert_any_call("A:dns-auth")

    def test_discovery_pool(self):
        """It should pool the correct service from DNS Discovery from the given site."""
        self.service1.discovery.pool("codfw")
        self.mocked_confctl.set_and_verify.assert_called_once_with("pooled", True, dnsdisc="(service1)", name="codfw")
        self.mocked_remote.query.assert_any_call("A:dns-auth")

    def test_discovery_pooled_ok(self):
        """It should depool, give control and repool the correct service from DNS Discovery from the given site."""
        with self.service1.discovery.depooled("codfw"):
            self.mocked_confctl.set_and_verify.assert_called_once_with(
                "pooled", False, dnsdisc="(service1)", name="codfw"
            )
            self.mocked_confctl.reset_mock()
        self.mocked_confctl.set_and_verify.assert_called_once_with("pooled", True, dnsdisc="(service1)", name="codfw")

    def test_discovery_pooled_raise(self):
        """It should not repool the given service if an exception is raised."""
        with pytest.raises(RuntimeError, match="some error"):
            with self.service1.discovery.depooled("codfw"):
                self.mocked_confctl.set_and_verify.assert_called_once_with(
                    "pooled", False, dnsdisc="(service1)", name="codfw"
                )
                self.mocked_confctl.reset_mock()
                raise RuntimeError("some error")
        self.mocked_confctl.set_and_verify.assert_not_called()

    def test_discovery_pooled_raise_repool(self):
        """It should repool the given service if an exception is raised but repool_on_error is True."""
        with pytest.raises(RuntimeError, match="some error"):
            with self.service1.discovery.depooled("codfw", repool_on_error=True):
                self.mocked_confctl.set_and_verify.assert_called_once_with(
                    "pooled", False, dnsdisc="(service1)", name="codfw"
                )
                self.mocked_confctl.reset_mock()
                raise RuntimeError("some error")
        self.mocked_confctl.set_and_verify.assert_called_once_with("pooled", True, dnsdisc="(service1)", name="codfw")

    def test_downtime(self, requests_mock):
        """It should downtime the service on Alertmanager for the given site."""
        requests_mock.post("/api/v2/silences", json={"silenceID": "a123"})
        reason = Reason("Maintenance", "user", "host")
        downtime_id = self.service1.downtime("codfw", reason)
        assert downtime_id == "a123"
        request_json = requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "site", "value": "codfw", "isRegex": False},
            {"name": "job", "value": r"^probes/.*", "isRegex": True},
            {"name": "instance", "value": "^(service1:443)$", "isRegex": True},
        ]

    def test_downtime_raise(self):
        """It should raise a ServiceError when trying to downtime a service in a site where is not present."""
        reason = Reason("Maintenance", "user", "host")
        with pytest.raises(
            service.ServiceError,
            match=r"Service service1 is not present in site nonexistent. Available sites are \['codfw', 'eqiad'\]",
        ):
            self.service1.downtime("nonexistent", reason)

    def test_downtimed(self, requests_mock):
        """It should allow to perform actions while the service is downtimed in the given site."""
        requests_mock.post("/api/v2/silences", json={"silenceID": "a123"})
        requests_mock.delete("/api/v2/silence/a123")
        reason = Reason("Maintenance", "user", "host")
        with self.service1.downtimed("codfw", reason):
            request_json = requests_mock.last_request.json()
            assert request_json["matchers"] == [
                {"name": "site", "value": "codfw", "isRegex": False},
                {"name": "job", "value": r"^probes/.*", "isRegex": True},
                {"name": "instance", "value": "^(service1:443)$", "isRegex": True},
            ]
        assert requests_mock.call_count == 2
        assert requests_mock.request_history[-1].method == "DELETE"
