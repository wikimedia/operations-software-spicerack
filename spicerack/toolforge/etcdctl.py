"""Wrapper around etcdctl handling parameters and such."""
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional, Tuple, Union, cast

from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHosts, RemoteHostsAdapter

logger = logging.getLogger(__name__)
SimpleType = Union[str, int, bool]


class HealthStatus(Enum):
    """Health status."""

    # TODO: rename the following with UPPERCASE names
    healthy = auto()  # pylint: disable=invalid-name
    unhealthy = auto()  # pylint: disable=invalid-name


@dataclass(frozen=True)
class EtcdClusterHealthStatus:
    """Etcd cluster health status."""

    global_status: HealthStatus
    members_status: Dict[str, HealthStatus]


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

    def get_cluster_health(self) -> EtcdClusterHealthStatus:
        """Gets the current etcd cluster health status."""
        args = self._base_args + ["cluster-health"]
        raw_results = self._remote_hosts.run_sync(" ".join(args))
        try:
            result = next(raw_results)[1].message().decode("utf8")
        except StopIteration as e:
            raise UnableToParseOutput("Got no results when trying to retrieve the etcdctl cluster health.") from e

        global_status = None
        members_status = {}
        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue

            # member <memberid> is <healthy|unhealthy>: got <healthy|unhealthy> result from <member_url>
            # ...
            # cluster is <healthy|unhealthy>
            if line.startswith("cluster is"):
                global_status = HealthStatus[line.rsplit(" ", 1)[-1]]
            else:
                _, member_id, _, raw_health_status, _ = line.split(" ", 4)
                # raw_health_status includes the ':'
                members_status[member_id] = HealthStatus[raw_health_status[:-1]]

        if global_status is None:
            raise UnableToParseOutput(f"Can't find the global cluster status in the cluster-health output: {result}")

        return EtcdClusterHealthStatus(global_status=cast(HealthStatus, global_status), members_status=members_status)

    def get_cluster_info(self) -> Dict[str, Dict[str, SimpleType]]:
        """Gets the current etcd cluster information."""
        args = self._base_args + ["member", "list"]
        raw_results = self._remote_hosts.run_sync(" ".join(args))
        try:
            result = next(raw_results)[1].message().decode("utf8")
        except StopIteration as e:
            raise UnableToParseOutput("Got no results when trying to retrieve the etcdctl members list.") from e

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
    def _to_simple_tuple(cls, elem: str) -> Tuple[str, SimpleType]:
        elems = elem.split("=", 1)
        if len(elems) != 2:
            raise UnableToParseOutput(f"Malformed element '{elem}', has no '='.")

        return (elems[0], cls._to_simple_type(elems[1]))

    @staticmethod
    def _get_member_or_none(
        members: Dict[str, Dict[str, SimpleType]], member_name: str, member_peer_url: Optional[str] = None
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
