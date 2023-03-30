"""Redfish module."""
import ipaddress
import json
import logging
import re
import time
from abc import abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from io import BufferedReader
from pathlib import Path
from typing import Any, Optional, Union

import urllib3
from packaging import version
from requests import Response
from requests.exceptions import RequestException
from wmflib.requests import http_session

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class RedfishError(SpicerackError):
    """General errors raised by this module."""


class RedfishTaskNotCompletedError(RedfishError):
    """Raised when a Redfish task is not found on the server."""


class ChassisResetPolicy(Enum):
    """Subset of available Chassis.Reset policies compatible with all supported vendors (at this moment only Dell)."""

    FORCE_OFF: str = "ForceOff"
    """Turn off the unit immediately (nongraceful shutdown)."""
    FORCE_RESTART: str = "ForceRestart"
    """Shut down immediately and nongracefully and restart the system."""
    GRACEFUL_RESTART: str = "GracefulRestart"
    """Shut down gracefully and power on."""
    GRACEFUL_SHUTDOWN: str = "GracefulShutdown"
    """Shut down gracefully and power off."""
    ON: str = "On"
    """Turn on the unit."""


class DellSCPRebootPolicy(Enum):
    """Available Dell SCP (Server Configuration Profiles) reboot policies."""

    FORCED: str = "Forced"
    """Issue an immediate hard reboot without notifying the operating system."""
    GRACEFUL: str = "Graceful"
    """Issue a reboot notifying the operating system."""
    NO_REBOOT: str = "NoReboot"
    """Do not reboot right now, the Redfish task will be pending the next reboot to apply the changes."""


class DellSCPPowerStatePolicy(Enum):
    """Available Dell SCP (Server Configuration Profiles) final power state after an operation policies."""

    OFF: str = "Off"
    """Keep the host powered off after the operation."""
    ON: str = "On"
    """Turn the host power back on after the operation."""


class DellSCPTargetPolicy(Enum):
    """Available sections of the Dell SCP (Server Configuration Profiles) to target."""

    ALL = "ALL"
    """All settings."""
    BIOS = "BIOS"
    """Only BIOS settings."""
    IDRAC = "IDRAC"
    """Only iDRAC settings."""
    NIC = "NIC"
    """Only network interfaces settings."""
    RAID = "RAID"
    """Only RAID controller settings."""


class Redfish:
    """Manage Redfish operations on a specific device."""

    def __init__(
        self,
        hostname: str,
        interface: Union[ipaddress.IPv4Interface, ipaddress.IPv6Interface],
        username: str,
        password: str,
        *,
        dry_run: bool = True,
    ):
        """Initialize the instance.

        Arguments:
            hostname: the hostname (not FQDN) the management console belongs to.
            interface: the interface of the management console to connect to.
            username: the API username.
            password: the API password.
            dry_run: whether this is a DRY-RUN.

        """
        self._dry_run = dry_run
        self._hostname = hostname
        self._interface = interface
        self._username = username
        self._password = password

        self._http_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=10)
        # TODO: evaluate if we should create an intermediate CA for managament consoles
        self._http_session.verify = False  # The devices have a self-signed certificate
        self._http_session.auth = (self._username, self._password)
        self._http_session.headers.update({"Accept": "application/json"})

        self._upload_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=60 * 30)
        self._upload_session.verify = False  # The devices have a self-signed certificate
        self._upload_session.auth = (self._username, self._password)
        self._upload_session.headers.update({"Accept": "application/json"})

        self._oob_info: dict = {}
        self._system_info: dict = {}
        self._updateservice_info: dict = {}

    def __str__(self) -> str:
        """String representation of the instance."""
        return f"{self._username}@{self._hostname} ({self._interface.ip})"

    @property
    @abstractmethod
    def system_manager(self) -> str:
        """Property to return the System manager."""

    @property
    @abstractmethod
    def oob_manager(self) -> str:
        """Property to return the Out of Band manager."""

    def _update_system_info(self) -> None:
        """Property to return a dict of manager metadata."""
        self._system_info = self.request("get", self.system_manager).json()

    def _update_oob_info(self) -> None:
        """Update the data Out of Band manager info."""
        self._oob_info = self.request("get", self.oob_manager).json()

    @property
    def update_service(self) -> str:
        """Property to return the Out of Band manager."""
        # for now this is the same for both dell and supermicro
        return "/redfish/v1/UpdateService"

    @property
    @abstractmethod
    def log_entries(self) -> str:
        """Property to return the uri for the log entries."""

    @property
    @abstractmethod
    def reboot_message_id(self) -> str:
        """Property to return the Message Id for reboot log entries."""

    @property
    def hostname(self) -> str:
        """Getter for the device hostname."""
        return self._hostname

    @property
    def interface(self) -> Union[ipaddress.IPv4Interface, ipaddress.IPv6Interface]:
        """Getter for the management interface address with netmask."""
        return self._interface

    @property
    def system_info(self) -> dict:
        """Property to return the system info as a dict."""
        if not self._system_info:
            self._update_system_info()
        return self._system_info

    @property
    def oob_info(self) -> dict:
        """Property to return the oob info as a dict."""
        if not self._oob_info:
            self._update_oob_info()
        return self._oob_info

    @property
    def updateservice_info(self) -> dict:
        """Property to return a dict of manager metadata."""
        if not self._updateservice_info:
            result = self.request("get", self.update_service)
            self._updateservice_info = result.json()
        return self._updateservice_info

    @property
    def oob_model(self) -> str:
        """Property to return a string representing the model."""
        return self.oob_info["Model"]

    @property
    def firmware_version(self) -> version.Version:
        """Property to return a version instance representing the firmware version."""
        self._update_oob_info()
        return version.parse(self.oob_info["FirmwareVersion"])

    @property
    def bios_version(self) -> version.Version:
        """Property to return a instance representing the Bios version."""
        self._update_system_info()
        return version.parse(self.system_info["BiosVersion"])

    @property
    def model(self) -> str:
        """Property to return a string representing the model."""
        return self.system_info["Model"]

    @property
    def manufacturer(self) -> str:
        """Property to return a string representing the model."""
        return self.system_info["Manufacturer"]

    @property
    def pushuri(self) -> str:
        """Property representing the HttpPushUri of the idrac for uploading firmwares to it."""
        try:
            return self.updateservice_info["HttpPushUri"]
        except KeyError:
            raise NotImplementedError from KeyError

    @property
    def multipushuri(self) -> str:
        """Property representing the MultipartHttpPushUri of the idrac for uploading firmwares to it."""
        return self.updateservice_info["MultipartHttpPushUri"]

    def upload_file(self, file_path: Path, reboot: bool = False) -> str:
        """Upload a file to the firmware directory via redfish and return the job_id URI.

        Arguments:
            file_path: The file path to upload.
            reboot: if true immediately reboot the server.

        """
        with file_path.open("rb") as file_handle:
            return self.multipush_upload(file_handle, file_path.name, reboot)

    def multipush_upload(self, file_handle: BufferedReader, filename: str, reboot: bool = False) -> str:
        """Upload a file via redfish and return its job_id URI.

        Arguments:
            file_handle: On open file handle to the object to upload.
            filename: filename name to use for upload.
            reboot: if true immediately reboot the server.

        """
        operation = "Immediate" if reboot else "OnReset"
        payload = {"Targets": [], "@Redfish.OperationApplyTime": operation, "Oem": {}}
        files = {
            "UpdateParameters": (None, json.dumps(payload), "application/json"),
            "UpdateFile": (filename, file_handle, "application/octet-stream"),
        }
        job_id = self.submit_files(files)
        logger.debug("upload has task ID: %s", job_id)
        return job_id

    @staticmethod
    def most_recent_member(members: list[dict], key: str) -> dict:
        """Return the most recent member of members result from dell api.

        Members will be sorted on key and the most recent value is returned.
        The value of key is assumed to be an iso date.

        Arguments:
            members: A list of dicts returned from the dell api.
            key: The key to search on.

        """

        def sorter(element: dict) -> datetime:
            """Sort by datetime."""
            return datetime.fromisoformat(element[key])

        return sorted(members, key=sorter)[-1]

    def last_reboot(self) -> datetime:
        """Get the the last reboot time."""
        # TODO: we can possibly use filter once all OOB's are updated.  e.g.
        # Lclog/Entries?$filter=MessageId eq 'reboot_code'
        # currently we get the following on some older models
        # Message=Querying is not supported by the implementation, MessageArgs=$filter"
        last_reboot = datetime.fromisoformat("1970-01-01T00:00:00-00:00")
        results = self.request("get", self.log_entries).json()
        # use ends with as sometimes there is an additional string prefix to the code e.g. IDRAC.2.7.RAC0182
        members = [m for m in results["Members"] if m["MessageId"].endswith(self.reboot_message_id)]
        if members:
            last_reboot = datetime.fromisoformat(self.most_recent_member(members, "Created")["Created"])
        logger.debug("%s: last reboot %s", self._hostname, last_reboot)
        return last_reboot

    @retry(
        tries=240,
        delay=timedelta(seconds=10),
        backoff_mode="constant",
        exceptions=(RedfishError,),
    )
    def wait_reboot_since(self, since: datetime) -> None:
        """Wait for idrac/redfish to become responsive.

        Arguments:
            since: The datetime of the last reboot.

        """
        self.check_connection()
        latest = self.last_reboot()
        if since >= latest:
            raise RedfishError("no new reboot detected")
        logger.debug("%s: new management console reboot detected %s", self._hostname, latest)

    def request(self, method: str, uri: str, **kwargs: Any) -> Response:
        """Perform a request against the target Redfish instance with the provided HTTP method and data.

        Arguments:
            uri: the relative URI to request.
            method: the HTTP method to use (e.g. "post").
            **kwargs: arbitrary keyword arguments, to be passed requests.

        Raises:
            spicerack.redfish.RedfishError: if the response status code is between 400 and 600 or if the given uri
            does not start with a slash (/) or if the request couldn't be performed.

        """
        if uri[0] != "/":
            raise RedfishError(f"Invalid uri {uri}, it must start with a /")

        url = f"https://{self._interface.ip}{uri}"

        if self._dry_run and method.lower() not in ("head", "get"):  # RW call
            logger.info("Would have called %s on %s", method, url)
            return self._get_dummy_response()

        try:
            response = self._http_session.request(method, url, **kwargs)
        except RequestException as e:
            message = f"Failed to perform {method.upper()} request to {url}"
            if self._dry_run:
                logger.error("%s: %s", message, e)
                return self._get_dummy_response()

            raise RedfishError(message) from e

        if not response.ok:
            raise RedfishError(
                f"{method.upper()} {url} returned HTTP {response.status_code} with message:\n{response.text}"
            )

        return response

    def _parse_submit_task(self, response: Response) -> str:
        """Submit a request that generates a task, return the URI of the submitted task.

        Arguments:
            response: the response to parse.

        Raises:
            spicerack.redfish.RedfishError: if the response status code is not 202 or there is no Location header.

        """
        uri = response.request.path_url
        if response.status_code != 202:
            raise RedfishError(
                f"Unable to start task for {uri}, expected HTTP 202, "
                f"got HTTP {response.status_code} instead:\n{response.text}"
            )

        # requests allow to access headers with any capitalization
        if "Location" not in response.headers or not response.headers["Location"]:
            raise RedfishError(
                "Unable to get the task URI to poll results for the {uri} request. Returned headers:\n"
                f"{response.headers}"
            )

        return response.headers["Location"]

    def submit_files(self, files: dict) -> str:
        """Submit a upload file request that generates a task, return the URI of the submitted task.

        Arguments:
            uri: the relative URI to request.
            files: the files to upload to send in the request.

        """
        if self._dry_run:
            return "/"

        # BUG: timeout is not honoured by self.request
        # response = self.request('post', self.multipushuri, files=files)
        response = self._upload_session.post(f"https://{self.interface.ip}{self.multipushuri}", files=files)
        return self._parse_submit_task(response)

    def submit_task(self, uri: str, data: Optional[dict] = None, method: str = "post") -> str:
        """Submit a request that generates a task, return the URI of the submitted task.

        Arguments:
            uri: the relative URI to request.
            data: the data to send in the request.
            method: the HTTP method to use, if not the default one.

        """
        if self._dry_run:
            return "/"

        response = self.request(method, uri, json=data)
        return self._parse_submit_task(response)

    def check_connection(self) -> None:
        """Check the connection with the Redfish API.

        Raises:
            spicerack.redfish.RedfishError: if unable to connect to Redfish API.

        """
        logger.info("Testing Redfish API connection to %s (%s)", self._hostname, self._interface.ip)
        self.request("get", "/redfish")

    @retry(
        tries=30,
        delay=timedelta(seconds=30),
        backoff_mode="constant",
        exceptions=(RedfishTaskNotCompletedError,),
        failure_message="Polling task",
    )
    def poll_task(self, uri: str) -> dict:
        """Poll a Redfish task until the results are available and return them.

        Arguments:
           uri: the URI of the task, usually returned as Location header by the originating API call.

        Raises:
            spicerack.redfish.RedfishError: if the response from the server is outside the expected values of HTTP
            200 or 202.
            spicearck.redfish.RedfishTaskNotCompletedError: if the task is not yet completed.

        """
        if self._dry_run:
            return {}

        response = self.request("get", uri)
        if response.status_code not in (200, 202):
            raise RedfishError(f"{uri} returned HTTP {response.status_code}:\n{response.text}")

        results = response.json()
        if response.status_code == 200 and "@odata.id" not in results:  # Task completed, got data without metadata
            return results

        for message in results["Messages"]:
            if "Oem" in message:
                continue  # Skip Oem messages, they might have any custom structure

            # Some older Dell implementation use both keys in the same API response :/
            message_id = message.get("MessageId", message.get("MessageID", "N.A."))
            logger.info("[%s] %s", message_id, message["Message"])

        try:
            end_time = datetime.fromisoformat(results.get("EndTime", "1970-01-01T00:00:00")).timestamp()
        except ValueError:
            # Endtime is TIME_NA
            end_time = 0

        if end_time == 0:
            raise RedfishTaskNotCompletedError(
                f"{results['Id']} not completed yet: status={results['TaskStatus']}, state={results['TaskState']}, "
                f"completed={results.get('PercentComplete', 'unknown')}%"
            )

        return results  # When a task is polled after returning the data, will return again the metadata

    def find_account(self, username: str) -> tuple[str, str]:
        """Find the account for the given username and return its URI.

        Arguments:
            username: the username to search for.

        Returns:
            A 2-element tuple with the URI for the account and the ETag header value of the GET response.

        Raises:
            spicerack.redfish.RedfishError: if unable to find the account.

        """
        accounts = self.request("get", f"{self.oob_manager}/Accounts").json()
        uris = [account["@odata.id"] for account in accounts["Members"]]
        for uri in uris:
            response = self.request("get", uri)
            if response.json()["UserName"] == username:
                return uri, response.headers.get("ETag", "")

        raise RedfishError(f"Unable to find account for username {username}")

    def change_user_password(self, username: str, password: str) -> None:
        """Change the password for the account with the given username.

        If the username matches the one used by the instance to connect to the API, automatically updates the instance
        value so that the instance will keep working.

        Arguments:
            username: the username to search for.
            password: the new password to set.

        Raises:
            spicerack.redfish.RedfishError: if unable to find the user or update its password.

        """
        user_uri, etag = self.find_account(username)
        logger.info("Changing password for the account with username %s: %s", username, user_uri)
        response = self.request(
            "patch", user_uri, json={"UserName": username, "Password": password}, headers={"If-Match": etag}
        )
        if response.status_code != 200:
            raise RedfishError(f"Got unexpected HTTP {response.status_code}, expected 200:\n{response.text}")

        if self._username == username and not self._dry_run:
            self._password = password
            self._http_session.auth = (self._username, self._password)
            logger.info("Updated current instance password to the new password")

        for message in response.json().get("@Message.ExtendedInfo", []):
            identifier = " ".join((message.get("MessageId", ""), message.get("Severity", ""))).strip()
            logger.info(
                "[%s] %s | Resolution: %s", identifier, message.get("Message", ""), message.get("Resolution", "")
            )

    def get_power_state(self) -> str:
        """Return the current power state of the device."""
        response = self.request("get", "/redfish/v1/Chassis/System.Embedded.1").json()
        return response["PowerState"]

    def chassis_reset(self, action: ChassisResetPolicy) -> None:
        """Perform a reset of the chassis power status.

        Arguments:
            action: the reset policy to use.

        Raises:
            spicerack.redfish.RedfishError: if unable to perform the reset.

        """
        logger.info("Resetting chassis power status for %s to %s", self._hostname, action.value)
        response = self.request(
            "post",
            "/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
            json={"ResetType": action.value},
        )
        if response.status_code != 204 and not self._dry_run:
            raise RedfishError(
                f"Got unexpected response HTTP {response.status_code}, expected HTTP 204: {response.text}"
            )

    @staticmethod
    def _get_dummy_response() -> Response:
        """Return a dummy requests's Response to be used in dry-run mode."""
        response = Response()
        response.status_code = 200
        return response


class DellSCP:
    """Reprenset a Dell System Configuration Profile configuration as returned by Redfish API."""

    def __init__(self, config: dict, target: DellSCPTargetPolicy, *, allow_new_attributes: bool = False):
        """Parse the Redfish API response.

        Arguments:
            config: the configuration as returned by Redfish API.
            target: describe which sections of the configuration are represented in the loaded configuration.
            allow_new_attributes: when set to :py:data:`True` it allows the creation of new attributes not
                already present in the provided configuration that otherwise would raise an exception. This is
                useful for example when changing the boot mode between Uefi and Bios that changes the keys present.

        """
        self._config = config
        self._target = target
        self._allow_new_attributes = allow_new_attributes
        # Track if the Components property have been emptied, allowing the creation of new components
        self._emptied_components = False

    @property
    def config(self) -> dict:
        """Getter for the whole configuration in Dell's format."""
        return self._config

    @property
    def target(self) -> DellSCPTargetPolicy:
        """Getter for the target that the current configuration represents."""
        return self._target

    @property
    def service_tag(self) -> str:
        """Getter for the device Dell's Service Tag."""
        return self._config["SystemConfiguration"]["ServiceTag"]

    @property
    def model(self) -> str:
        """Getter for the device Dell's model."""
        return self._config["SystemConfiguration"]["Model"]

    @property
    def timestamp(self) -> datetime:
        """Getter for the timestamp when the configuration dump was generated."""
        return datetime.strptime(self._config["SystemConfiguration"]["TimeStamp"], "%c")

    @property
    def comments(self) -> list[str]:
        """Getter for the comments associated with the configuration."""
        return [
            comment["Comment"]
            for comment in self._config["SystemConfiguration"].get("Comments", [])
            if "Comment" in comment
        ]

    @property
    def components(self) -> dict[str, dict[str, str]]:
        """Getter for the components present in the configuration in a simplified view.

        The returned dictionary where all the keys are recursively sorted and has the following format::

            {
                '<component name>': {
                    'key1': 'value1',
                    'key2': 'value2',
                },
            }

        """
        components: dict[str, dict[str, str]] = {}
        for component in self._config["SystemConfiguration"].get("Components", []):
            components[component["FQDD"]] = {}
            for attribute in component.get("Attributes", []):
                components[component["FQDD"]][attribute["Name"]] = attribute["Value"]

        # Sort the components recursively
        return {component: dict(sorted(components[component].items())) for component in sorted(components)}

    def set(self, component_name: str, attribute_name: str, attribute_value: str) -> bool:
        """Update the current configuration setting to the new value for the given key in the given component.

        Notes:
            This updates only the instance representation of the instance. To push and apply the changes to the server
            see :py:meth:`spicerack.redfish.RedfishDell.scp_push`.
            In order to add attributes not present the instance must have been created with `allow_new_attributes` set
            to :py:data:`True` or the :py:meth:`spicerack.redfish.DellSCP.empty_component` method called. This last one
            allows to automatically create any missing component while setting attributes.

        Arguments:
            component_name: the name of the component the settings belongs to.
            attribute_name: the attribute name whose value needs to be updated.
            attribute_value: the new value for the attribute to set.

        Returns:
            :py:data:`True` if the value was added or changed, :py:data:`False` if it had already the correct value.

        Raises:
            spicerack.redfish.RedfishError: if unable to find the given component or attribute and the creation of new
            items is not allowed.

        """

        def new_attribute() -> dict[str, str]:
            """Local helper that returns a new attribute to append to the component."""
            attribute = {
                "Name": attribute_name,
                "Value": attribute_value,
                "Set On Import": "True",
                "Comment": "Read and Write",
            }
            logger.info(
                "Created attribute %s -> %s (with Set On Import True) with value %s",
                component_name,
                attribute_name,
                attribute_value,
            )
            return attribute

        for component in self._config["SystemConfiguration"]["Components"]:
            if component["FQDD"] != component_name:
                continue

            for i in range(len(component["Attributes"])):
                attribute = component["Attributes"][i]
                if attribute["Name"] != attribute_name:
                    continue

                # Attribute found, update it if different, consider comma-separated lists identical with both ',' and
                # ', ' as separators.
                if attribute["Value"].replace(", ", ",") == attribute_value.replace(", ", ","):
                    logger.info(
                        "Skipped set of attribute %s -> %s, has already the correct value: %s",
                        component_name,
                        attribute_name,
                        attribute["Value"],
                    )
                    return False

                logger.info(
                    "Updated value for attribute %s -> %s%s: %s => %s",
                    component_name,
                    attribute_name,
                    " (marked Set On Import to True)" if attribute["Set On Import"] == "False" else "",
                    attribute["Value"],
                    attribute_value,
                )
                attribute["Value"] = attribute_value
                attribute["Set On Import"] = "True"

                return True

            # Attribute not found, add it or raise
            if self._allow_new_attributes or self._emptied_components:
                component["Attributes"].append(new_attribute())
                return True

            raise RedfishError(f"Unable to find attribute {component_name} -> {attribute_name}")

        # Component not found, add it or raise
        if self._emptied_components:
            self._config["SystemConfiguration"]["Components"].append(
                {"FQDD": component_name, "Attributes": [new_attribute()]}
            )
            return True

        raise RedfishError(f"Unable to find component {component_name}")

    def update(self, changes: dict[str, dict[str, str]]) -> bool:
        """Bulk update the current configuration with the set of changes provided.

        Notes:
            This updates only the instance representation of the instance. To push and apply the changes to the server
            see :py:meth:`spicerack.redfish.RedfishDell.scp_push`.

        Arguments:
            changes: a dictionary of changes to apply in the same format of the one returned by
                :py:meth:`spicerack.redfish.DellSCP.components`.

        Returns:
            :py:data:`True` if any of the values produced a change, :py:data:`False` if no change was made.

        Raises:
            spicerack.redfish.RedfishError: if unable to apply all the changes.

        """
        was_changed = False
        for component, attributes in changes.items():
            for name, value in attributes.items():
                was_changed |= self.set(component, name, value)

        return was_changed

    def empty_components(self) -> None:
        """Empty the current Components from the configuration, allowing to create a new configuration from scratch.

        After calling this method is possible to set values for non-existing components that would otherwise raise an
        exception.

        """
        self._config["SystemConfiguration"]["Components"] = []
        self._emptied_components = True


class RedfishSupermicro(Redfish):
    """Redfish class for SuperMicro servers."""

    @property
    def system_manager(self) -> str:
        """Property to return the System manager."""
        return "/redfish/v1/Systems/1"

    @property
    def oob_manager(self) -> str:
        """String representing the Out of Band manager key."""
        return "/redfish/v1/Managers/1"

    @property
    def log_entries(self) -> str:
        """String representing the log entries uri."""
        return "/redfish/v1/Managers/1/LogServices/Log1/Entries"

    @property
    def reboot_message_id(self) -> str:
        """String representing the message Id of the reboot."""
        return "Event.1.0.SystemPowerAction"


class RedfishDell(Redfish):
    """Dell specific Redfish support."""

    scp_base_uri: str = "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/EID_674_Manager"
    """The Dell's SCP push base URI."""

    def __init__(
        self,
        hostname: str,
        interface: Union[ipaddress.IPv4Interface, ipaddress.IPv6Interface],
        username: str,
        password: str,
        *,
        dry_run: bool = True,
    ):
        """Override parent's constructor."""
        super().__init__(hostname, interface, username, password, dry_run=dry_run)
        self._generation = 0

    @property
    def system_manager(self) -> str:
        """Property to return the System manager."""
        return "/redfish/v1/Systems/System.Embedded.1"

    @property
    def oob_manager(self) -> str:
        """String representing the Out of Band manager key."""
        return "/redfish/v1/Managers/iDRAC.Embedded.1"

    @property
    def log_entries(self) -> str:
        """String representing the log entries uri."""
        if self.firmware_version < version.Version("4.10"):
            return "/redfish/v1/Managers/Logs/Lclog"
        return "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries"

    @property
    def reboot_message_id(self) -> str:
        """String representing the message Id of the reboot."""
        return "RAC0182"

    @property
    def generation(self) -> int:
        """Property representing the generation of the idrac.

        This is often 13 for idrac8 and 14 for idrac9.  This property allows us to add workarounds
        for older idrac models
        """
        if self._generation == 0:
            match = re.search(r"\d+", self.oob_model)
            if match is None:
                logger.error("%s: Unrecognized iDRAC model %s, setting generation to 1", self._hostname, self.oob_model)
                # Setting this to one allows use to continue but assumes the minimal level of support
                self._generation = 1
            else:
                self._generation = int(match.group(0))
        logger.debug("%s: iDRAC generation %s", self._hostname, self._generation)
        return self._generation

    @retry(
        tries=240,
        delay=timedelta(seconds=10),
        backoff_mode="constant",
        exceptions=(RedfishError,),
    )
    def wait_reboot_since(self, since: datetime) -> None:
        """Wait for idrac/redfish to become responsive.

        Arguments:
            since: the datetime of the last reboot.

        """
        self.check_connection()
        if self._generation < 14:
            # Probing the Gen13/iDRAC8 devices too early seems to cause the redfish deamon to crash
            print("sleeping for 2 mins to let idrac boot")
            time.sleep(120)
        latest = self.last_reboot()
        if since >= latest:
            raise RedfishError("no new reboot detected")
        logger.debug("%s: new management console reboot detected %s", self._hostname, latest)
        # Its still takes a bit of time for redfish to fully come only so
        # We just arbitrarily sleep for a bit
        sleep_secs = 30
        logger.debug("%s: sleeping for %d secs", self._hostname, sleep_secs)
        time.sleep(sleep_secs)

    def scp_dump(
        self, target: DellSCPTargetPolicy = DellSCPTargetPolicy.ALL, *, allow_new_attributes: bool = False
    ) -> DellSCP:
        """Dump and return the SCP (Server Configuration Profiles) configuration.

        Arguments:
            target: choose which sections to dump.
            allow_new_attributes: when set to :py:data:`True` it allows the creation of new attributes not
                already present in the retrieved configuration that otherwise would raise an exception. This is
                useful for example when changing the boot mode between Uefi and Bios that changes the keys present.

        Raises:
            spicerack.redfish.RedfishError: if the API call fail.
            spicerack.redfish.RedfishTaskNotCompletedError: if unable to fetch the dumped results.

        """
        data = {"ExportFormat": "JSON", "ShareParameters": {"Target": target.value}}
        task_uri = self.submit_task(f"{self.scp_base_uri}.ExportSystemConfiguration", data)

        return DellSCP(self.poll_task(task_uri), target, allow_new_attributes=allow_new_attributes)

    def scp_push(
        self,
        scp: DellSCP,
        *,
        reboot: DellSCPRebootPolicy = DellSCPRebootPolicy.NO_REBOOT,
        power_state: DellSCPPowerStatePolicy = DellSCPPowerStatePolicy.ON,
        preview: bool = True,
    ) -> dict:
        """Push the SCP (Server Configuration Profiles) configuration.

        Arguments:
            scp: the configuration that will pushed to the server.
            reboot: which reboot policy to use to apply the changes.
            power_state: which final power state policy to use to apply to the host after the changes have been
                applied.
            preview: if :py:data:`True` perform a test push of the SCP data. This will tell if the file
                parses correctly and would not result in any writes. The comments will tell if the new configuration
                would not produce any changes. Forces the reboot parameter to be
                :py:const:`spicerack.redfish.DellSCPRebootPolicy.NO_REBOOT`.

        Returns:
            The results of the push operation.

        Raises:
            spicerack.redfish.RedfishError: if the API call fail.
            spicerack.redfish.RedfishTaskNotCompletedError: if unable to fetch the dumped results.

        """
        if preview:
            uri = "ImportSystemConfigurationPreview"
            reboot = DellSCPRebootPolicy.NO_REBOOT
        else:
            uri = "ImportSystemConfiguration"

        data = {
            "ImportBuffer": json.dumps(scp.config),  # The API requires a JSON-encoded string inside a JSON payload.
            "ShareParameters": {"Target": scp.target.value},
            "HostPowerState": power_state.value,
            "ShutdownType": reboot.value,
        }

        task_id = self.submit_task(f"{self.scp_base_uri}.{uri}", data)

        return self.poll_task(task_id)
