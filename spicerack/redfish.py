"""Redfish module."""
import json
import logging
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import urllib3
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

    def __init__(self, fqdn: str, username: str, password: str, *, dry_run: bool = True):
        """Initialize the instance.

        Arguments:
            fqdn (str): the FQDN of the management console to connect to.
            username (str): the API username.
            password (str): the API password.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._dry_run = dry_run
        self._fqdn = fqdn
        self._username = username
        self._password = password
        self._http_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=10)
        # TODO: evaluate if we should create an intermediate CA for managament consoles
        self._http_session.verify = False  # The devices have a self-signed certificate
        self._http_session.auth = (self._username, self._password)
        self._http_session.headers.update({"Accept": "application/json"})
        self._generation = 0
        self._pushuri = ""

    def __str__(self) -> str:
        """String representation of the instance.

        Returns:
            str: the string representation of the target hosts.

        """
        return f"{self._username}@{self._fqdn}"

    @property
    def fqdn(self) -> str:
        """Getter for the fully qualified domain name.

        Returns
            str: the fqdn

        """
        return self._fqdn

    @property
    def generation(self) -> int:
        """Property representing the generation of the idrac.

        This is often 13 for idrac8 and 14 for idrac9.  This property allows us to add workarounds
        for older idrac models

        Returns:
            int: representing the generation

        """
        if not self._generation:
            result = self.request("get", "/redfish/v1/Managers/iDRAC.Embedded.1?$select=Model")
            model = result.json()["Model"]
            # Model e.g. '13G Monolithic'
            match = re.search(r"\d+", model)
            if match is None:
                logger.error("%s: Unrecognized model %s, setting generation to 1", self._fqdn, model)
                # Setting this to one allows use to continue but assumes the minimal level of support
                self._generation = 1
            else:
                self._generation = int(match.group(0))
        logger.debug("%s: iDRAC generation %s", self._fqdn, self._generation)
        return self._generation

    @property
    def pushuri(self) -> str:
        """Property representing the HttpPushUri of the idrac.

        This property is used for uploading firmwares to the idrac

        Returns:
            str: representing the HttpPushUri

        """
        if not self._pushuri:
            result = self.request("get", "/redfish/v1/UpdateService?$select=HttpPushUri")
            self._pushuri = result.json()["HttpPushUri"]
        logger.debug("%s: iDRAC PushUri %s", self._fqdn, self._pushuri)
        return self._pushuri

    @staticmethod
    def most_recent_member(members: List[Dict], key: str) -> Dict:
        """Return the most recent member of members result from dell api.

        Members will be sorted on key and the most recent value is returned.
        The value of key is assumed to be an iso date.

        Arguments:
            members: A list of dicts returned from the dell api.
            key: The key to search on.

        Returns:
            dict: the most recent member

        """

        def sorter(element: Dict) -> datetime:
            return datetime.fromisoformat(element[key])

        return sorted(members, key=sorter)[-1]

    def last_reboot(self) -> datetime:
        """Ask redfish for the last reboot time.

        Returns:
            datetime: the datetime of the last reboot event

        """
        # TODO: we can possibly use filter once all idrac are updated.  e.g.
        # iDRAC.Embedded.1/LogServices/Lclog/Entries?$filter=MessageId eq 'RAC0182'
        # currently we get the following on some older models
        # Message=Querying is not supported by the implementation, MessageArgs=$filter"
        last_reboot = datetime.fromisoformat("1970-01-01T00:00:00-00:00")
        results = self.request(
            "get",
            "/redfish/v1/Managers/iDRAC.Embedded.1/Logs/Lclog",
        ).json()
        # idrac reboots have the message_id RAC0182
        members = [m for m in results["Members"] if m["MessageId"] == "RAC0182"]
        if members:
            last_reboot = datetime.fromisoformat(self.most_recent_member(members, "Created")["Created"])
        logger.debug("%s: last_reboot %s", self._fqdn, last_reboot)
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
            since: The datetime of the last reboot

        """
        self.check_connection()
        if self._generation < 14:
            # Probing the Gen13/iDRAC8 devices too early seems to cause the redfish deamon to crash
            print("sleeping for 2 mins to let idrac boot")
            time.sleep(120)
        latest = self.last_reboot()
        if since >= latest:
            raise RedfishError("no new reboot detected")
        logger.debug("%s: new reboot detected %s", self._fqdn, latest)
        # Its still takes a bit of time for redfish to fully come only so
        # We just arbitrarily sleep for a bit
        sleep_secs = 30
        logger.debug("%s: sleeping for %d secs", self._fqdn, sleep_secs)
        time.sleep(sleep_secs)

    def request(self, method: str, uri: str, **kwargs: Any) -> Response:
        """Perform a request against the target Redfish instance with the provided HTTP method and data.

        Arguments:
            uri (str): the relative URI to request.
            method (str): the HTTP method to use (e.g. "post").
            **kwargs (mixed): arbitrary keyword arguments, to be passed requests

        Returns:
            requests.models.Response: the response.

        Raises:
            RedfishError: if the response status code is between 400 and 600 or if the given uri does not start with
            a slash (/) or if the request couldn't be performed.

        """
        if uri[0] != "/":
            raise RedfishError(f"Invalid uri {uri}, it must start with a /")

        url = f"https://{self._fqdn}{uri}"

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

    def submit_task(self, uri: str, data: Optional[Dict] = None, method: str = "post") -> str:
        """Submit a request that generates a task, return the URI of the submitted task.

        Arguments:
            uri (str): the relative URI to request.
            data (dict, optional): the data to send in the request.
            method (str, optional): the HTTP method to use, if not the default one.

        Returns:
            str: the URI of the task ID to poll the results.

        Raises:
            spicerack.redfish.RedfishError: if the response status code is not 202 or there is no Location header.

        """
        if self._dry_run:
            return "/"

        response = self.request(method, uri, json=data)
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

    def check_connection(self) -> None:
        """Check the connection with the Redfish API.

        Raises:
            spicerack.redfish.RedfishError: if unable to connect to Redfish API.

        """
        logger.info("Testing Redfish API connection to %s", self._fqdn)
        self.request("get", "/redfish")

    @retry(
        tries=30,
        delay=timedelta(seconds=30),
        backoff_mode="constant",
        exceptions=(RedfishTaskNotCompletedError,),
        failure_message="Polling task",
    )
    def poll_task(self, uri: str) -> Dict:
        """Poll a Redfish task until the results are available.

        Arguments:
           uri (str): the URI of the task, usually returned as Location header by the originating API call.

        Returns:
            dict: the task results.

        Raises:
            RedfishError: if the response from the server is outside the expected values of HTTP 200 or 202.
            RedfishTaskNotCompletedError: if the task is not yet completed.

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

    def find_account(self, username: str) -> Tuple[str, str]:
        """Find the account for the given username and return its URI.

        Arguments:
            username (str): the username to search for.

        Returns:
            tuple: a 2-element tuple with the URI for the account and the ETag header value of the GET response.

        Raises:
            spicerack.redfish.RedfishError: if unable to find the account.

        """
        accounts = self.request("get", "/redfish/v1/Managers/iDRAC.Embedded.1/Accounts").json()
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
            username (str): the username to search for.
            password (str): the new password to set.

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
        """Return the current power state of the device.

        Returns:
            str: the power state.

        """
        response = self.request("get", "/redfish/v1/Chassis/System.Embedded.1").json()
        return response["PowerState"]

    def chassis_reset(self, action: ChassisResetPolicy) -> None:
        """Perform a reset of the chassis power status.

        Arguments:
            action (spicerack.redfish.ChassisResetPolicy): the reset policy to use.

        Raises:
            spicerack.redfish.RedfishError: if unable to perform the reset.

        """
        logger.info("Resetting chassis power status for %s to %s", self._fqdn, action.value)
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
        """Return a dummy requests's Response to be used in dry-run mode.

        Returns:
            requests.Response: the dummy response.

        """
        response = Response()
        response.status_code = 200
        return response


class DellSCP:
    """Reprenset a Dell System Configuration Profile configuration as returned by Redfish API."""

    def __init__(self, config: Dict, target: DellSCPTargetPolicy, *, allow_new_attributes: bool = False):
        """Parse the Redfish API response.

        Arguments:
            config (dict): the configuration as returned by Redfish API.
            target (spicerack.redfish.DellSCPTargetPolicy): describe which sections of the configuration are
                represented in the loaded configuration.
            allow_new_attributes (bool): when set to :py:data:`True` it allows the creation of new attributes not
                already present in the provided configuration that otherwise would raise an exception. This is
                useful for example when changing the boot mode between Uefi and Bios that changes the keys present.

        """
        self._config = config
        self._target = target
        self._allow_new_attributes = allow_new_attributes
        # Track if the Components property have been emptied, allowing the creation of new components
        self._emptied_components = False

    @property
    def config(self) -> Dict:
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
    def comments(self) -> List[str]:
        """Getter for the comments associated with the configuration."""
        return [
            comment["Comment"]
            for comment in self._config["SystemConfiguration"].get("Comments", [])
            if "Comment" in comment
        ]

    @property
    def components(self) -> Dict[str, Dict[str, str]]:
        """Getter for the components present in the configuration in a simplified view.

        The returned dictionary where all the keys are recursively sorted and has the following format::

            {
                '<component name>': {
                    'key1': 'value1',
                    'key2': 'value2',
                },
            }

        """
        components: Dict[str, Dict[str, str]] = {}
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
            component_name (str): the name of the component the settings belongs to.
            attribute_name (str): the attribute name whose value needs to be updated.
            attribute_value (str): the new value for the attribute to set.

        Returns:
            bool: :py:data:`True` if the value was added or changed, :py:data:`False` if it had already the correct
            value.

        Raises:
            spicerack.redfish.RedfishError: if unable to find the given component or attribute and the creation of new
            items is not allowed.

        """

        def new_attribute() -> Dict[str, str]:
            """Local helper that returns a new attribute.

            Returns:
                dict: the attribute to append to the component.

            """
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

    def update(self, changes: Dict[str, Dict[str, str]]) -> bool:
        """Bulk update the current configuration with the set of changes provided.

        Notes:
            This updates only the instance representation of the instance. To push and apply the changes to the server
            see :py:meth:`spicerack.redfish.RedfishDell.scp_push`.

        Arguments:
            changes (dict): a dictionary of changes to apply in the same format of the one returned by
                :py:meth:`spicerack.redfish.DellSCP.components`.

        Returns:
            bool: :py:data:`True` if any of the values produced a change, :py:data:`False` if no change was made.

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


class RedfishDell(Redfish):
    """Dell specific Redfish support."""

    scp_base_uri = "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/EID_674_Manager"

    def scp_dump(
        self, target: DellSCPTargetPolicy = DellSCPTargetPolicy.ALL, *, allow_new_attributes: bool = False
    ) -> DellSCP:
        """Dump and return the SCP (Server Configuration Profiles) configuration.

        Arguments:
            target (spicerack.redfish.DellSCPTargetPolicy, optional): choose which sections to dump.
            allow_new_attributes (bool): when set to :py:data:`True` it allows the creation of new attributes not
                already present in the retrieved configuration that otherwise would raise an exception. This is
                useful for example when changing the boot mode between Uefi and Bios that changes the keys present.

        Returns:
            spicerack.redfish.DellSCP: the server's configuration.

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
    ) -> Dict:
        """Push the SCP (Server Configuration Profiles) configuration.

        Arguments:
            scp (spicerack.redfish.DellSCP): the configuration that will pushed to the server.
            reboot (spicerack.redfish.DellSCPRebootPolicy, optional): which reboot policy to use to apply the changes.
            power_state (spicerack.redfish.DellSCPPowerStatePolicy, optional): which final power state policy to use to
                apply to the host after the changes have been applied.
            preview (bool, optional): if :py:data:`True` perform a test push of the SCP data. This will tell if the file
                parses correctly and would not result in any writes. The comments will tell if the new configuration
                would not produce any changes. Forces the reboot parameter to be
                :py:const:`spicerack.redfish.DellSCPRebootPolicy.NO_REBOOT`.

        Returns:
            dict: the results of the push operation.

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
