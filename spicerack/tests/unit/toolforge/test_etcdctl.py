"""Toolforge etcdctl module tests."""
from typing import Any, List, Optional
from unittest import TestCase, mock

from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, NodeSet

from spicerack.remote import RemoteHosts
from spicerack.toolforge.etcdctl import EtcdctlController, TooManyHosts, UnableToParseOutput


def _assert_called_with_single_param(param: str, mock_obj: mock.MagicMock, num_calls: int = 1) -> None:
    mock_obj.assert_called()
    assert len(mock_obj.call_args_list) == num_calls
    for call in mock_obj.mock_calls:
        if param in call[1]:
            return

    assert False, f"Parameter {param} was never passed to any call to {mock_obj}: {mock_obj.mock_calls}"


def _assert_not_called_with_single_param(param: str, mock_obj: mock.MagicMock) -> None:
    mock_obj.assert_called_once()
    for call in mock_obj.mock_calls:
        if param in call[1]:
            assert False, f"Parameter {param} was passed on a call to {mock_obj}: {call}"


def _assert_called_with_double_param(param: str, value: Any, mock_obj: mock.MagicMock) -> None:
    _assert_called_with_single_param(param, mock_obj)
    args: List[Any] = []
    for call in mock_obj.mock_calls:
        if param in call[1]:
            args = call[1]

    first_param_pos = args.index(param) + 1
    gotten_value = args[first_param_pos]
    assert gotten_value == value


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

        _assert_called_with_double_param(
            param="--cert-file",
            value=expected_cert_file,
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

        _assert_called_with_double_param(
            param="--ca-file",
            value=expected_ca_file,
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

        _assert_called_with_double_param(
            param="--key-file",
            value=expected_key_file,
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

        _assert_called_with_double_param(
            param="--endpoints",
            value=expected_endpoints,
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

        _assert_called_with_single_param(param="update", mock_obj=mock_run_sync, num_calls=2)
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

        _assert_called_with_single_param(param="add", mock_obj=mock_run_sync, num_calls=3)
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

        _assert_called_with_single_param(param=expected_peer_url, mock_obj=mock_run_sync, num_calls=3)
