"""Wrapper around etcdctl handling parameters and such."""

import json
import logging
from typing import Optional, Union, cast

from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHosts, RemoteHostsAdapter

logger = logging.getLogger(__name__)
SimpleType = Union[str, int, bool]


class TooManyHosts(SpicerackError):
    """Raised when there's more hosts than supported passed."""


class UnableToParseOutput(SpicerackError):
    """Raised when there's an error trying to parse etcdctl output."""


class EtcdctlController(RemoteHostsAdapter):
    """Node that is able to run etcdctl and control an etcd cluster."""

    def __init__(self, *, remote_host: RemoteHosts):
        """Init."""
        if len(remote_host.hosts) > 1:
            raise TooManyHosts("EtcdctlController currently only supports running in one node.")

        super().__init__(remote_hosts=remote_host)

        endpoints = f"https://{self._remote_hosts.hosts}:2379"
        cert_file = f"/etc/etcd/ssl/{self._remote_hosts.hosts}.pem"
        ca_file = "/etc/etcd/ssl/ca.pem"
        key_file = f"/etc/etcd/ssl/{self._remote_hosts.hosts}.priv"
        self._base_args = [
            "ETCDCTL_API=3",
            "etcdctl",
            "--endpoints",
            endpoints,
            "--cacert",
            ca_file,
            "--cert",
            cert_file,
            "--key",
            key_file,
        ]

    def get_cluster_info(self) -> dict[str, dict[str, SimpleType]]:
        """Gets the current etcd cluster information."""
        args = [*self._base_args, "member", "list", "-w=json"]
        raw_results = self._remote_hosts.run_sync(" ".join(args))
        try:
            result = next(raw_results)[1].message().decode("utf8")
        except StopIteration as e:
            raise UnableToParseOutput("Got no results when trying to retrieve the etcdctl members list.") from e

        members = json.loads(result.strip()).get("members", []) if result else []
        structured_result = {}

        for member in members:
            if "ID" not in member:
                raise UnableToParseOutput(f"Unable to parse etcdctl output (missing ID)\nFull output: {result}")

            if "peerURLs" not in member:
                raise UnableToParseOutput(
                    f"Unable to parse etcdctl output (missing peerURLs)\nFull output: {result}"
                )

            struct_elem: dict[str, SimpleType] = {}

            decimal_id = member["ID"]
            member_id = format(int(decimal_id), "x")
            struct_elem["member_id"] = member_id
            name = member.get("name", "")
            if name:
                struct_elem["name"] = name
            clienturls = member.get("clientURLs", [""])[0]
            if clienturls:
                struct_elem["clientURLs"] = clienturls
            peerurls = member.get("peerURLs", [""])[0]
            struct_elem["peerURLs"] = peerurls

            struct_elem["status"] = "up" if "clientURLs" in struct_elem else "unstarted"

            structured_result[member_id] = struct_elem

        return structured_result

    def ensure_node_exists(
        self,
        new_member_fqdn: str,
        member_peer_url: Optional[str] = None,
    ) -> str:
        """Ensure the existance of an etcd member adding it if not present.

        Makes sure that the given new_member_fqdn member exists and is part of
        the etcd cluster, and returns its member id.
        """
        if not member_peer_url:
            member_peer_url = f"https://{new_member_fqdn}:2380"

        before_members = self.get_cluster_info()
        current_entry = self._get_member_or_none(
            members=before_members,
            member_name=new_member_fqdn,
            member_peer_url=member_peer_url,
        )
        extra_args = None

        if current_entry and current_entry["peerURLs"] == member_peer_url:
            logger.info(
                "Skipping addition of member %s as it already exists.",
                new_member_fqdn,
            )
            return cast(str, current_entry["member_id"])

        if current_entry and current_entry["peerURLs"] != member_peer_url:
            logger.info(
                "Updating url for already existing member %s.",
                new_member_fqdn,
            )
            extra_args = [
                "member",
                "update",
                cast(str, current_entry["member_id"]),
                member_peer_url,
            ]

        else:
            extra_args = ["member", "add", new_member_fqdn, "--peer-urls", member_peer_url]

        self._remote_hosts.run_sync(" ".join(self._base_args + extra_args))

        if not current_entry:
            # unfortunately, etcdctl add does not give the member_id, but only the new
            # name, so we have to diff before and after to find out which one is the
            # new member id
            after_members = self.get_cluster_info()
            new_member_id = list(set(after_members.keys()) - set(before_members.keys()))[0]

        else:
            new_member_id = cast(str, current_entry["member_id"])

        return new_member_id

    def ensure_node_does_not_exist(
        self,
        member_fqdn: str,
    ) -> Optional[str]:
        """Ensure the non existance of an etcd member, removing it if present.

        Makes sure that the given member_fqdn member is not part of the etcd
        cluster, returns its old member id or None if it was not there.
        """
        before_members = self.get_cluster_info()
        current_entry = self._get_member_or_none(
            members=before_members,
            member_name=member_fqdn,
        )

        if not current_entry:
            logger.info(
                "Skipping removal of member %s as it does not exist.",
                member_fqdn,
            )
            return None

        logger.info("Removing etcd member %s.", member_fqdn)
        extra_args = ["member", "remove", str(current_entry["member_id"])]
        self._remote_hosts.run_sync(" ".join(self._base_args + extra_args))
        return str(current_entry["member_id"])

    @staticmethod
    def _to_simple_type(maybe_not_string: str) -> SimpleType:
        """Simple type interpolation, etcdctl member list does not return json."""
        if maybe_not_string == "true":
            return True

        if maybe_not_string == "false":
            return False

        try:
            return int(maybe_not_string)

        except ValueError:
            pass

        return maybe_not_string

    @classmethod
    def _to_simple_tuple(cls, elem: str) -> tuple[str, SimpleType]:
        elems = elem.split("=", 1)
        if len(elems) != 2:
            raise UnableToParseOutput(f"Malformed element '{elem}', has no '='.")

        return (elems[0], cls._to_simple_type(elems[1]))

    @staticmethod
    def _get_member_or_none(
        members: dict[str, dict[str, SimpleType]], member_name: str, member_peer_url: Optional[str] = None
    ) -> dict[str, SimpleType]:
        return next(
            (
                member
                for member in members.values()
                if (
                    ("name" in member
                    and member["name"] == member_name)
                    # in case the member is not started, it does not show the name,
                    # just the peer url
                    or ("name" not in member
                    and member["peerURLs"] == member_peer_url)
                )
            ),
            {},
        )
