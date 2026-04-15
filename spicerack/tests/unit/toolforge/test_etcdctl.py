"""Toolforge etcdctl module tests."""

from typing import Optional
from unittest import TestCase, mock

from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, nodeset

from spicerack.remote import RemoteHosts
from spicerack.toolforge.etcdctl import EtcdctlController, TooManyHosts, UnableToParseOutput


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
                raise AssertionError("Parameter {param} was passed on a call to {mock_obj}: {call}")


def _get_mock_run_sync(
    return_value: Optional[bytes] = None, side_effect: Optional[list[bytes]] = None
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
        nodes = RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test[0,1].local.host"))

        with self.assertRaises(TooManyHosts):
            EtcdctlController(remote_host=nodes)


class TestGetClusterInfo(TestCase):
    """TestGetClusterInfo."""

    def test_passes_correct_cert_file(self):
        """Test that passes correct cert file by default."""
        expected_cert_file = "/etc/etcd/ssl/test0.local.host.pem"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--cert {expected_cert_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_ca_file(self):
        """Test that passes correct ca file by default."""
        expected_ca_file = "/etc/etcd/ssl/ca.pem"
        mock_run_sync = _get_mock_run_sync(return_value=b"{}")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--cacert {expected_ca_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_key_file(self):
        """Test that passes correct key file by default."""
        expected_key_file = "/etc/etcd/ssl/test0.local.host.priv"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            controller.get_cluster_info()

        _assert_called_with_single_param(
            param=f"--key {expected_key_file}",
            mock_obj=mock_run_sync,
        )

    def test_passes_correct_endpoints(self):
        """Test that passes correct endpoints by default."""
        expected_endpoints = "https://test0.local.host:2379"
        mock_run_sync = _get_mock_run_sync(return_value=b"")
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
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
            "peerURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380",
            "clientURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379",
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]}]}
                            """,
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
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
                "peerURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "clientURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379",
            },
            "5208bbf5c00e7cdf": {
                "clientURLs": "https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379",
                "member_id": "5208bbf5c00e7cdf",
                "name": "toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud",
                "peerURLs": "https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "status": "up",
            },
        }
        mock_run_sync = _get_mock_run_sync(
            return_value=b"""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"ID":5911181175087332575,"name":"toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2379"]}]}
                            """,
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
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
                "peerURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "clientURLs": "https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379",
            },
            "5208bbf5c00e7cdf": {
                "member_id": "5208bbf5c00e7cdf",
                "name": "toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud",
                "peerURLs": "https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380",
                "status": "unstarted",
            },
        }
        mock_run_sync = _get_mock_run_sync(return_value=b"""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"ID":5911181175087332575,"name":"toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380"]}]}
                """)
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.get_cluster_info()

        mock_run_sync.assert_called_once()
        assert expected_result == gotten_result

    def test_raises_when_getting_member_without_id(self):
        """Test that raises when getting member without id."""
        mock_run_sync = _get_mock_run_sync(return_value=b"""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"name":"toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-6.toolsbeta.eqiad1.wikimedia.cloud:2380"]}]}
            """)
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with self.assertRaises(UnableToParseOutput):
            with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
                controller.get_cluster_info()


class TestEnsureNodeExists(TestCase):
    """TestEnsureNodeExists."""

    def test_skips_addition_if_member_already_exists(self):
        """Test that skips addition if member already exists."""
        existing_member_fqdn = "ialreadyexist"
        existing_member_peer_url = f"https://{existing_member_fqdn}:1234"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(return_value=("""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"ID":"%s","name":"%s","peerURLs":["%s"]}]}
""" % (expected_member_id, existing_member_fqdn, existing_member_peer_url)).encode())
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_member_id = controller.ensure_node_exists(
                new_member_fqdn=existing_member_fqdn,
                member_peer_url=existing_member_peer_url,
            )

        _assert_called_with_single_param(param="list", mock_obj=mock_run_sync)
        _assert_not_called_with_single_param(param="add", mock_obj=mock_run_sync)
        assert gotten_member_id == format(int(expected_member_id), "x")

    def test_updates_the_member_if_the_peer_url_does_not_match(self):
        """Test that updates the member if the peer url does not match."""
        existing_member_fqdn = "ialreadyexist"
        existing_member_peer_url = f"https://{existing_member_fqdn}:1234"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                ("""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"ID":"%s","name":"%s","peerURLs":["%s_differs"]}]}
""" % (expected_member_id, existing_member_fqdn, existing_member_peer_url)).encode(),
                b"""Updated :)""",
                ("""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"ID":"%s","name":"%s","peerURLs":["%s"]}]}
""" % (expected_member_id, existing_member_fqdn, existing_member_peer_url)).encode(),
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_member_id = controller.ensure_node_exists(
                new_member_fqdn=existing_member_fqdn,
                member_peer_url=existing_member_peer_url,
            )

        _assert_called_with_single_param(param="update", mock_obj=mock_run_sync)
        assert gotten_member_id == format(int(expected_member_id), "x")

    def test_adds_the_member_if_not_there(self):
        """Test that adds the member if not there."""
        new_member_fqdn = "ialreadyexist"
        new_member_peer_url = f"https://{new_member_fqdn}:1234"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                ("""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]}]}
""").encode(),
                b"""Added :)""",
                ("""
{"header":{"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},"members":[{"ID":4706420839500714067,"name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud","peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],"clientURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]},{"ID":"%s","name":"%s","peerURLs":["%s"]}]}
""" % (expected_member_id, new_member_fqdn, new_member_peer_url)).encode(),
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_member_id = controller.ensure_node_exists(
                new_member_fqdn=new_member_fqdn,
                member_peer_url=new_member_peer_url,
            )

        _assert_called_with_single_param(param="add", mock_obj=mock_run_sync)
        assert gotten_member_id == format(int(expected_member_id), "x")

    def test_uses_default_member_url_if_not_passed(self):
        """Test that uses default member url if not passed."""
        new_member_fqdn = "ialreadyexist"
        expected_peer_url = f"https://{new_member_fqdn}:2380"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                b"",
                b"""Added :)""",
                (
                    """{"header":
                           {"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},
                        "members":
                            [{"ID":4706420839500714067,"name":"%s","peerURLs":["%s"]}]}"""
                    % (new_member_fqdn, expected_peer_url)
                ).encode(),
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
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
        mock_run_sync = _get_mock_run_sync(return_value="""
                    {"header":
                      {"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},
                     "members":
                       [{"ID":4706420839500714067,
                         "name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud",
                         "peerURLs":["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],
                         "clientURLs":
                           ["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]}]}""".encode())
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
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
        member_fqdn = "ialreadyexist"
        expected_member_id = "1234556789012345"
        mock_run_sync = _get_mock_run_sync(
            side_effect=[
                (
                    (
                        """
                            {"header":
                                {"cluster_id":13161044974788149663,"member_id":4706420839500714067,"raft_term":164389},
                             "members":
                                 [{"ID":4706420839500714067,
                                   "name":"toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud",
                                   "peerURLs":
                                     ["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2380"],
                                   "clientURLs":
                                     ["https://toolsbeta-test-k8s-etcd-9.toolsbeta.eqiad1.wikimedia.cloud:2379"]}
                                 ,{"ID":"%s","name":"%s","peerURLs":"http://some.url"}]}"""
                        % (expected_member_id, member_fqdn)
                    ).encode()
                ),
                "Removed :)",
            ]
        )
        controller = EtcdctlController(
            remote_host=RemoteHosts(config=mock.MagicMock(specset=Config), hosts=nodeset("test0.local.host")),
        )

        with mock.patch.object(RemoteHosts, "run_sync", mock_run_sync):
            gotten_result = controller.ensure_node_does_not_exist(member_fqdn=member_fqdn)

        _assert_called_with_single_param(param="remove", mock_obj=mock_run_sync)
        assert gotten_result == format(int(expected_member_id), "x")
