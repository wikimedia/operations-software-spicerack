"""Toolforge etcdctl module tests."""
from typing import List, Optional
from unittest import TestCase, mock

from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, NodeSet

from spicerack.remote import RemoteHosts
from spicerack.toolforge.etcdctl import EtcdctlController, HealthStatus, TooManyHosts, UnableToParseOutput


def _assert_called_with_single_param(param: str, mock_obj: mock.MagicMock) -> None:
    mock_obj.assert_called()
    call_count = 0
    for call in mock_obj.mock_calls:
        for arg in call[1]:
            if isinstance(arg, str) and param in arg:
                call_count += 1

    assert (
        call_count == 1
    ), f"Expected to have 1 call with param {param}, but got {call_count}, all calls: {mock_obj.mock_calls}"


def _assert_not_called_with_single_param(param: str, mock_obj: mock.MagicMock) -> None:
    mock_obj.assert_called_once()
    for call in mock_obj.mock_calls:
        for arg in call[1]:
            if isinstance(arg, str) and param in arg:
                assert False, f"Parameter {param} was passed on a call to {mock_obj}: {call}"


def _get_mock_run_sync(
    return_value: Optional[bytes] = None, side_effect: Optional[List[bytes]] = None
) -> mock.MagicMock:
    if side_effect is not None:
        return mock.MagicMock(
            side_effect=[
                (
                    iter(
                        [
                            ("test0.local.host", MsgTreeElem(return_value, parent=MsgTreeElem())),
                        ]
                    )
                )
                for return_value in side_effect
            ]
        )

    return mock.MagicMock(return_value=iter([("test0.local.host", MsgTreeElem(return_value, parent=MsgTreeElem()))]))


class TestEtcdctlController(TestCase):
    """TestEtcdctlController."""

    def test_raises_if_more_than_one_node_is_used(self):
        """Test that raises if more than one node is used."""
        nodes = RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test[0,1].local.host"))

        with self.assertRaises(TooManyHosts):
            EtcdctlController(remote_host=nodes)


class TestGetHealth(TestCase):
    """TestGetHealth."""

    def test_passes_correct_cert_file(self):
        """Test that passes correct cert file by default."""
        expected_cert_file = "/etc/etcd/ssl/test0.local.host.pem"
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_health()

        _assert_called_with_single_param(
            param=f"--cert-file {expected_cert_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_ca_file(self):
        """Test that passes correct ca file by default."""
        expected_ca_file = "/etc/etcd/ssl/ca.pem"
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_health()

        _assert_called_with_single_param(
            param=f"--ca-file {expected_ca_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_key_file(self):
        """Test that passes correct key file by default."""
        expected_key_file = "/etc/etcd/ssl/test0.local.host.priv"
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_health()

        _assert_called_with_single_param(
            param=f"--key-file {expected_key_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_endpoints(self):
        """Test that passes correct endpoints by default."""
        expected_endpoints = "https://test0.local.host:2379"
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_health()

        _assert_called_with_single_param(
            param=f"--endpoints {expected_endpoints}",
            mock_obj=mock_run_sync,
        )

    def test_parses_result_with_one_member(self):
        """Test that parses result with one member."""
        expected_members = {"415090d15def9053": HealthStatus.healthy}
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_health()

        mock_run_sync.assert_called_once()
        assert gotten_result.members_status == expected_members

    def test_parses_result_with_many_members(self):
        """Test that parses result with many members."""
        expected_members = {
            "415090d15def9053": HealthStatus.healthy,
            "5208bbf5c00e7cdf": HealthStatus.healthy,
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                member 5208bbf5c00e7cdf is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_health()

        mock_run_sync.assert_called_once()
        assert expected_members == gotten_result.members_status

    def test_parses_result_with_member_down(self):
        """Test that parses result with member down."""
        expected_members = {
            "415090d15def9053": HealthStatus.healthy,
            "5208bbf5c00e7cdf": HealthStatus.unhealthy,
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 415090d15def9053 is healthy: got healthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                member 5208bbf5c00e7cdf is unhealthy: got unhealthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_health()

        mock_run_sync.assert_called_once()
        assert expected_members == gotten_result.members_status

    def test_gets_cluster_healthy(self):
        """Test that parses cluster global status when healthy."""
        expected_global_status = HealthStatus.healthy
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 5208bbf5c00e7cdf is unhealthy: got unhealthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is healthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_health()

        mock_run_sync.assert_called_once()
        assert expected_global_status == gotten_result.global_status

    def test_gets_cluster_unhealthy(self):
        """Test that parses cluster global status when unhealthy."""
        expected_global_status = HealthStatus.unhealthy
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 5208bbf5c00e7cdf is unhealthy: got unhealthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
                cluster is unhealthy
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_health()

        mock_run_sync.assert_called_once()
        assert expected_global_status == gotten_result.global_status

    def test_raises_when_no_global_cluster_health(self):
        """Test that parses cluster global status when unhealthy."""
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                member 5208bbf5c00e7cdf is unhealthy: got unhealthy result from https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379
            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            with self.assertRaises(UnableToParseOutput):
                controller.get_cluster_health()

        mock_run_sync.assert_called_once()


class TestGetClusterInfo(TestCase):
    """TestGetClusterInfo."""

    def test_passes_correct_cert_file(self):
        """Test that passes correct cert file by default."""
        expected_cert_file = "/etc/etcd/ssl/test0.local.host.pem"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--cert-file {expected_cert_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_ca_file(self):
        """Test that passes correct ca file by default."""
        expected_ca_file = "/etc/etcd/ssl/ca.pem"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--ca-file {expected_ca_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_key_file(self):
        """Test that passes correct key file by default."""
        expected_key_file = "/etc/etcd/ssl/test0.local.host.priv"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--key-file {expected_key_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_endpoints(self):
        """Test that passes correct endpoints by default."""
        expected_endpoints = "https://test0.local.host:2379"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--endpoints {expected_endpoints}",
            mock_obj=mock_run_sync,
        )

    def test_parses_result_with_one_member(self):
        """Test that parses result with one member."""
        expected_node = {
            "member_id": "415090d15def9053",
            "name": "toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud",
            "status": "up",
            "isLeader": True,
            "peerURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380",
            "clientURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379",
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                                415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_info()

        mock_run_sync.assert_called_once()
        assert len(gotten_result) == 1
        assert expected_node["member_id"] in gotten_result
        assert gotten_result[expected_node["member_id"]] == expected_node

    def test_parses_result_with_many_members(self):
        """Test that parses result with many members."""
        expected_result = {
            "415090d15def9053": {
                "member_id": "415090d15def9053",
                "name": "toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud",
                "status": "up",
                "isLeader": True,
                "peerURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "clientURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379",
            },
            "5208bbf5c00e7cdf": {
                "clientURLs": "https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379",
                "isLeader": False,
                "member_id": "5208bbf5c00e7cdf",
                "name": "toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud",
                "peerURLs": "https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "status": "up",
            },
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                                415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                                5208bbf5c00e7cdf: name=toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=false
                            """,  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_info()

        mock_run_sync.assert_called_once()
        assert expected_result == gotten_result

    def test_parses_result_with_member_down(self):
        """Test that parses result with member down."""
        expected_result = {
            "415090d15def9053": {
                "member_id": "415090d15def9053",
                "name": "toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud",
                "status": "up",
                "isLeader": True,
                "peerURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "clientURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379",
            },
            "cf612c785df58f6a": {
                "member_id": "cf612c785df58f6a",
                "peerURLs": "https://idontexist.localhost:1234",
                "status": "unstarted",
            },
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                cf612c785df58f6a[unstarted]: peerURLs=https://idontexist.localhost:1234
            """  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_info()

        mock_run_sync.assert_called_once()
        assert expected_result == gotten_result

    def test_raises_when_getting_member_without_id(self):
        """Test that raises when getting member without id."""
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
                415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                peerURLs=https://idontexist.localhost:1234
            """  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with self.assertRaises(UnableToParseOutput):
            with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
                controller.get_cluster_info()


class TestEnsureNodeExists(TestCase):
    """TestEnsureNodeExists."""

    def test_skips_addition_if_member_already_exists(self):
        """Test that skips addition if member already exists."""
        existing_member_fqdn = "i.already.exist"
        existing_member_peer_url = f"https://{existing_member_fqdn}:1234"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            return_value=f"""
                415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                {expected_member_id}: name={existing_member_fqdn} peerURLs={existing_member_peer_url}
            """.encode()  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_member_id = controller.ensure_node_exists(
                new_member_fqdn=existing_member_fqdn,
                member_peer_url=existing_member_peer_url,
            )

        _assert_called_with_single_param(param="list", mock_obj=mock_run_sync)
        _assert_not_called_with_single_param(param="add", mock_obj=mock_run_sync)
        assert gotten_member_id == expected_member_id

    def test_updates_the_member_if_the_peer_url_does_not_match(self):
        """Test that updates the member if the peer url does not match."""
        existing_member_fqdn = "i.already.exist"
        existing_member_peer_url = f"https://{existing_member_fqdn}:1234"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                f"""
                    415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                    {expected_member_id}: name={existing_member_fqdn} peerURLs={existing_member_peer_url}_but_different
                """.encode(),  # noqa: E501
                b"""Updated :)""",
                f"""
                    415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=false
                    {expected_member_id}: name={existing_member_fqdn} peerURLs={existing_member_peer_url}
                """.encode(),  # noqa: E501
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_member_id = controller.ensure_node_exists(
                new_member_fqdn=existing_member_fqdn,
                member_peer_url=existing_member_peer_url,
            )

        _assert_called_with_single_param(param="update", mock_obj=mock_run_sync)
        assert gotten_member_id == expected_member_id

    def test_adds_the_member_if_not_there(self):
        """Test that adds the member if not there."""
        new_member_fqdn = "i.already.exist"
        new_member_peer_url = f"https://{new_member_fqdn}:1234"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                b"""
                    415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
                """,  # noqa: E501
                b"""Added :)""",
                f"""
                    415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=false
                    {expected_member_id}: name={new_member_fqdn} peerURLs={new_member_peer_url}
                """.encode(),  # noqa: E501
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_member_id = controller.ensure_node_exists(
                new_member_fqdn=new_member_fqdn,
                member_peer_url=new_member_peer_url,
            )

        _assert_called_with_single_param(param="add", mock_obj=mock_run_sync)
        assert gotten_member_id == expected_member_id

    def test_uses_default_member_url_if_not_passed(self):
        """Test that uses default member url if not passed."""
        new_member_fqdn = "i.already.exist"
        expected_peer_url = f"https://{new_member_fqdn}:2380"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                b"",
                b"""Added :)""",
                f"""
                    415090d15def9053: name={new_member_fqdn} peerURLs={expected_peer_url}
                """.encode(),
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.ensure_node_exists(new_member_fqdn=new_member_fqdn)

        _assert_called_with_single_param(param=expected_peer_url, mock_obj=mock_run_sync)


class TestEnsureNodeDoesNotExist(TestCase):
    """TestEnsureNodeDoesNotExist."""

    def test_skips_removal_if_member_does_not_exist(self):
        """Test that skips removal if member does not exist."""
        non_existing_member_fqdn = "i.dont.exist"
        expected_result = None
        mock_run_sync = _get_mock_run_sync(
            return_value="""
                415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=true
            """.encode()  # noqa: E501
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.ensure_node_does_not_exist(
                member_fqdn=non_existing_member_fqdn,
            )

        _assert_called_with_single_param(param="list", mock_obj=mock_run_sync)
        _assert_not_called_with_single_param(param="remove", mock_obj=mock_run_sync)
        assert gotten_result == expected_result

    def test_removes_the_member_if_there_already(self):
        """Test that it removes the member if there already."""
        member_fqdn = "i.already.exist"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                f"""
                    415090d15def9053: name=toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud peerURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380 clientURLs=https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379 isLeader=false
                    {expected_member_id}: name={member_fqdn} peerURLs=http://some.url
                """.encode(),  # noqa: E501
                "Removed :)",
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=NodeSet("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.ensure_node_does_not_exist(member_fqdn=member_fqdn)

        _assert_called_with_single_param(param="remove", mock_obj=mock_run_sync)
        assert gotten_result == expected_member_id
