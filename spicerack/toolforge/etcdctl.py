"""Wrapper around etcdctl handling parameters and such."""
# pylint: disable=unsubscriptable-object,too-many-arguments
import logging
from typing import Dict, Optional, Tuple, Union, cast

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
            "etcdctl",
            "--endpoints",
            endpoints,
            "--ca-file",
            ca_file,
            "--cert-file",
            cert_file,
            "--key-file",
            key_file,
        ]

    def get_cluster_info(self) -> Dict[str, Dict[str, SimpleType]]:
        """Gets the current etcd cluster information."""
        args = self._base_args + ["member", "list"]
        raw_results = self._remote_hosts.run_sync(*args)
        try:
            result = next(raw_results)[1].message().decode("utf8")
        except StopIteration:
            raise UnableToParseOutput("Got no results when trying to retrieve the etcdctl members list.")

        structured_result = {}
        for line in result.split("\n"):
            if not line.strip():
                continue

            # <memberid>[<status>]: <key>=<value> <key>=<value>...
            # where value might be the string "true" or a stringified int "42"
            # and the '[<status>]' bit might not be there
            # peerURLs and memberid are the only key that seems to be there always
            split_info = [self._to_simple_tuple(elem) for elem in line.split(":", 1)[-1].split()]
            struct_elem: Dict[str, SimpleType] = dict(split_info)

            first_part = line.split(":", 1)[0].strip()
            if "[" in first_part:
                member_id = first_part.split("[", 1)[0]
                status = first_part.split("[", 1)[1][:-1]
            else:
                member_id = first_part
                status = "up"

            struct_elem["member_id"] = member_id
            struct_elem["status"] = status

            if "peerURLs" not in struct_elem:
                raise UnableToParseOutput(
                    "Unable to parse etcdctl output (missing peerURLs for "
                    f"member line):\nParsed: {struct_elem}\nLine: {line}\n"
                    f"Full output: {result}"
                )
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
            extra_args = ["member", "add", new_member_fqdn, member_peer_url]

        self._remote_hosts.run_sync(*(self._base_args + extra_args))

        if not current_entry:
            # unfortunately, etcdctl add does not give the member_id, but only the new
            # name, so we have to diff before and after to find out which one is the
            # new member id
            after_members = self.get_cluster_info()
            new_member_id = list(set(after_members.keys()) - set(before_members.keys()))[0]

        else:
            new_member_id = cast(str, current_entry["member_id"])

        return new_member_id

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
    def _to_simple_tuple(cls, elem: str) -> Tuple[str, SimpleType]:
        elems = elem.split("=", 1)
        if len(elems) != 2:
            raise UnableToParseOutput(f"Malformed element '{elem}', has no '='.")

        return (elems[0], cls._to_simple_type(elems[1]))

    @staticmethod
    def _get_member_or_none(
        members: Dict[str, Dict[str, SimpleType]], member_name: str, member_peer_url: str
    ) -> Dict[str, SimpleType]:
        return next(
            (
                member
                for member in members.values()
                if (
                    "name" in member
                    and member["name"] == member_name
                    # in case the member is not started, it does not show the name,
                    # just the peer url
                    or "name" not in member
                    and member["peerURLs"] == member_peer_url
                )
            ),
            {},
        )
