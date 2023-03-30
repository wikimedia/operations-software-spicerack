"""Netbox module tests."""
import ipaddress
import logging
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest
import requests
from packaging import version

from spicerack import redfish

ACCOUNTS_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#ManagerAccountCollection.ManagerAccountCollection",
    "@odata.id": "/redfish/v1/AccountService/Accounts",
    "@odata.type": "#ManagerAccountCollection.ManagerAccountCollection",
    "Description": "BMC User Accounts Collection",
    "Members": [
        {"@odata.id": "/redfish/v1/AccountService/Accounts/1"},
        {"@odata.id": "/redfish/v1/AccountService/Accounts/2"},
        {"@odata.id": "/redfish/v1/AccountService/Accounts/3"},
    ],
    "Members@odata.count": 3,
    "Name": "Accounts Collection",
}
ACCOUNT_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#ManagerAccount.ManagerAccount",
    "@odata.id": "/redfish/v1/AccountService/Accounts/{user_id}",
    "@odata.type": "#ManagerAccount.v1_5_0.ManagerAccount",
    "AccountTypes": ["Redfish", "SNMP", "OEM"],
    "Description": "User Account",
    "Enabled": True,
    "Id": "{user_id}",
    "Links": {"Role": {"@odata.id": "/redfish/v1/AccountService/Roles/Administrator"}},
    "Locked": False,
    "Name": "User Account",
    "OEMAccountTypes": ["IPMI", "SOL", "WSMAN", "UI", "RACADM"],
    "Password": None,
    "PasswordChangeRequired": False,
    "RoleId": "Administrator",
    "SNMP": {
        "AuthenticationKey": None,
        "AuthenticationKeySet": True,
        "AuthenticationProtocol": "HMAC_SHA96",
        "EncryptionKey": None,
        "EncryptionKeySet": False,
        "EncryptionProtocol": "CFB128_AES128",
    },
    "UserName": "username",
}
DELL_SCP = {
    "SystemConfiguration": {
        "Comments": [{"Comment": "First comment"}],
        "Components": [
            {
                "Attributes": [
                    {
                        "Comment": "Read and Write",
                        "Name": "Some.Attribute.2",
                        "Set On Import": "False",
                        "Value": "value",
                    },
                    {
                        "Comment": "Read and Write",
                        "Name": "Some.Attribute.1",
                        "Set On Import": "False",
                        "Value": "value",
                    },
                ],
                "FQDD": "Some.Component.2",
            },
            {
                "Attributes": [
                    {
                        "Comment": "Read and Write",
                        "Name": "Some.Attribute.1",
                        "Set On Import": "False",
                        "Value": "value",
                    },
                ],
                "FQDD": "Some.Component.1",
            },
            {
                "Attributes": [
                    {
                        "Comment": "Read and Write",
                        "Name": "Comma.Separated.List.1",
                        "Set On Import": "False",
                        "Value": "value1,value2",
                    },
                    {
                        "Comment": "Read and Write",
                        "Name": "Comma.Space.Separated.List.1",
                        "Set On Import": "False",
                        "Value": "value1, value2",
                    },
                ],
                "FQDD": "List.Component.1",
            },
        ],
        "Model": "PowerEdge R440",
        "ServiceTag": "12ABC34",
        "TimeStamp": "Thu Dec  9 09:32:06 2021",
    },
}
DELL_TASK_REPONSE = {
    "@odata.context": "/redfish/v1/$metadata#Task.Task",
    "@odata.id": "/redfish/v1/TaskService/Tasks/JID_1234567890",
    "@odata.type": "#Task.v1_1_1.Task",
    "Description": "Server Configuration and other Tasks running on iDRAC are listed here",
    "EndTime": "TIME_NA",
    "Id": "JID_1234567890",
    "Messages": [
        {
            "Oem": {
                "Custom": "Structure",
            },
        },
        {
            "Message": "Exporting Server Configuration Profile.",
            "MessageArgs": [],
            "MessageArgs@odata.count": 0,
            "MessageId": "SYS057",
        },
        {
            "Message": "Successfully exported Server Configuration Profile",
            "MessageArgs": [],
            "MessageArgs@odata.count": 0,
            "MessageID": "SYS043",
        },
    ],
    "Messages@odata.count": 1,
    "Name": "Export: Server Configuration Profile",
    "StartTime": "2021-12-09T14:36:29-06:00",
    "TaskState": "Running",
    "TaskStatus": "OK",
}
DELL_TASK_REPONSE_EPOC = deepcopy(DELL_TASK_REPONSE)
DELL_TASK_REPONSE_EPOC["EndTime"] = "1969-12-31T18:00:00-06:00"
DELL_TASK_REPONSE_BAD_TIME = deepcopy(DELL_TASK_REPONSE)
DELL_TASK_REPONSE_BAD_TIME["EndTime"] = "bad value"
MANAGER_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#Manager.Manager",
    "@odata.id": "/redfish/v1/Managers/Testing_oob.1",
    "@odata.type": "#Manager.v1_12_0.Manager",
    "Actions": {
        "#Manager.Reset": {
            "ResetType@Redfish.AllowableValues": ["GracefulRestart"],
            "target": "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Manager.Reset",
        },
        "#Manager.ResetToDefaults": {
            "ResetType@Redfish.AllowableValues": ["ResetAll", "PreserveNetworkAndUsers"],
            "target": "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Manager.ResetToDefaults",
        },
    },
    "DateTime": "2023-01-30T14:23:51-06:00",
    "DateTimeLocalOffset": "-06:00",
    "Description": "BMC",
    "EthernetInterfaces": {"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/EthernetInterfaces"},
    "FirmwareVersion": "6.00.30.00",
    "HostInterfaces": {"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/HostInterfaces"},
    "Id": "iDRAC.Embedded.1",
    "LastResetTime": "2022-11-17T17:56:11-06:00",
    "LogServices": {"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices"},
    "ManagerType": "BMC",
    "Model": "14G Monolithic",
    "Name": "Manager",
    "NetworkProtocol": {"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/NetworkProtocol"},
    "PowerState": "On",
    "SerialConsole": {
        "ConnectTypesSupported": [],
        "ConnectTypesSupported@odata.count": 0,
        "MaxConcurrentSessions": 0,
        "ServiceEnabled": False,
    },
    "SerialInterfaces": {"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/SerialInterfaces"},
    "Status": {"Health": "OK", "State": "Enabled"},
}
MANAGER_RESPONSE_V3 = deepcopy(MANAGER_RESPONSE)
MANAGER_RESPONSE_V3["FirmwareVersion"] = "3.0.0.0"
MANAGER_RESPONSE_BAD = deepcopy(MANAGER_RESPONSE)
MANAGER_RESPONSE_BAD["Model"] = "Foobar"
LCLOG_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#LogEntryCollection.LogEntryCollection",
    "@odata.id": "/redfish/v1/Managers/Testing_oob.1/LogServices/Lclog/Entries",
    "@odata.type": "#LogEntryCollection.LogEntryCollection",
    "Description": "LC Logs for this manager",
    "Members": [
        {
            "@odata.id": "/redfish/v1/Managers/Testing_oob.1/LogServices/Lclog/Entries/1735",
            "@odata.type": "#LogEntry.v1_6_1.LogEntry",
            "Created": "2022-06-22T17:01:17-05:00",
            "Description": "Log Entry 1735",
            "EntryType": "Oem",
            "Id": "1735",
            "Links": {"OriginOfCondition": {"@odata.id": "/redfish/v1/Managers/Testing_oob.1"}},
            "Message": "Successfully logged in using root, from " "10.192.32.49 and REDFISH.",
            "MessageArgs": ["root", "10.192.32.49", "REDFISH"],
            "MessageArgs@odata.count": 3,
            "MessageId": "USR0030",
            "Name": "Log Entry 1735",
            "Oem": {
                "Dell": {
                    "@odata.type": "#DellLCLogEntry.v1_0_0.DellLCLogEntry",
                    "Category": "Audit",
                    "Comment": None,
                    "LastUpdatedByUser": None,
                }
            },
            "OemRecordFormat": "Dell",
            "Severity": "OK",
        },
        {
            "@odata.id": "/redfish/v1/Managers/Testing_oob.1/LogServices/Lclog/Entries/1734",
            "@odata.type": "#LogEntry.v1_6_1.LogEntry",
            "Created": "2022-06-22T16:58:17-05:00",
            "Description": "Log Entry 1734",
            "EntryType": "Oem",
            "Id": "1734",
            "Links": {},
            "Message": "The (installation or configuration) job " "JID_559308065328 is successfully completed.",
            "MessageArgs": ["JID_559308065328"],
            "MessageArgs@odata.count": 1,
            "MessageId": "JCP037",
            "Name": "Log Entry 1734",
            "Oem": {
                "Dell": {
                    "@odata.type": "#DellLCLogEntry.v1_0_0.DellLCLogEntry",
                    "Category": "Configuration",
                    "Comment": None,
                    "LastUpdatedByUser": None,
                }
            },
            "OemRecordFormat": "Dell",
            "Severity": "OK",
        },
        {
            "@odata.id": "/redfish/v1/Managers/Testing_oob.1/LogServices/Lclog/Entries/1692",
            "@odata.type": "#LogEntry.v1_6_1.LogEntry",
            "Created": "2022-06-22T16:42:55-05:00",
            "Description": "Log Entry 1692",
            "EntryType": "Oem",
            "Id": "1692",
            "Links": {},
            "Message": "The iDRAC firmware was rebooted with the " "following reason: user initiated.",
            "MessageArgs": ["user initiated"],
            "MessageArgs@odata.count": 1,
            "MessageId": "REBOOT_MSG_ID",
            "Name": "Log Entry 1692",
            "Oem": {
                "Dell": {
                    "@odata.type": "#DellLCLogEntry.v1_0_0.DellLCLogEntry",
                    "Category": "Audit",
                    "Comment": None,
                    "LastUpdatedByUser": None,
                }
            },
            "OemRecordFormat": "Dell",
            "Severity": "OK",
        },
    ],
    "Members@odata.count": 1735,
    "Members@odata.nextLink": "/redfish/v1/Managers/Testing_oob.1/LogServices/Lclog/Entries?$skip=50",
    "Name": "Log Entry Collection",
}

LCLOG_RESPONSE_NO_MESSAGE = deepcopy(LCLOG_RESPONSE)
LCLOG_RESPONSE_NO_MESSAGE["Members"] = []
# The below is trimmed output
SYSTEM_MANAGER_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#ComputerSystem.ComputerSystem",
    "@odata.id": "/redfish/v1/Systems/System.Embedded.1",
    "@odata.type": "#ComputerSystem.v1_16_0.ComputerSystem",
    "Actions": {
        "#ComputerSystem.Reset": {
            "ResetType@Redfish.AllowableValues": [
                "On",
                "ForceOff",
                "ForceRestart",
                "GracefulRestart",
                "GracefulShutdown",
                "PushPowerButton",
                "Nmi",
                "PowerCycle",
            ],
            "target": "/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
        }
    },
    "AssetTag": "",
    "Bios": {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/Bios"},
    "BiosVersion": "2.15.1",
    "EthernetInterfaces": {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces"},
    "HostName": "",
    "HostWatchdogTimer": {"FunctionEnabled": False, "Status": {"State": "Disabled"}, "TimeoutAction": "None"},
    "HostingRoles": [],
    "HostingRoles@odata.count": 0,
    "Id": "System.Embedded.1",
    "IndicatorLED": "Lit",
    "LastResetTime": "2023-01-23T09:35:39-06:00",
    "Manufacturer": "Dell Inc.",
    "Model": "PowerEdge R440",
    "Name": "System",
    "NetworkInterfaces": {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/NetworkInterfaces"},
    "PowerState": "On",
    "Status": {"Health": "OK", "HealthRollup": "OK", "State": "Enabled"},
    "SystemType": "Physical",
    "UUID": "4c4c4544-0058-3810-8032-b2c04f525032",
}
UPDATE_SERVICE_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#UpdateService.UpdateService",
    "@odata.id": "/redfish/v1/UpdateService",
    "@odata.type": "#UpdateService.v1_11_0.UpdateService",
    "FirmwareInventory": {"@odata.id": "/redfish/v1/UpdateService/FirmwareInventory"},
    "HttpPushUri": "/redfish/v1/UpdateService/FirmwareInventory",
    "Id": "UpdateService",
    "MaxImageSizeBytes": None,
    "MultipartHttpPushUri": "/redfish/v1/UpdateService/MultipartUpload",
    "Name": "Update Service",
    "ServiceEnabled": True,
    "SoftwareInventory": {"@odata.id": "/redfish/v1/UpdateService/SoftwareInventory"},
    "Status": {"Health": "OK", "State": "Enabled"},
}
UPDATE_SERVICE_RESPONSE_NO_HTTP_PUSH = deepcopy(UPDATE_SERVICE_RESPONSE)
del UPDATE_SERVICE_RESPONSE_NO_HTTP_PUSH["HttpPushUri"]


def add_accounts_mock_responses(requests_mock):
    """Setup requests mock URLs and return payloads for all the existing users."""
    requests_mock.get("/redfish/v1/Managers/Testing_oob.1/Accounts", json=ACCOUNTS_RESPONSE)
    users = {"1": "user", "2": "root", "3": "guest"}
    for user_id, username in users.items():
        response = deepcopy(ACCOUNT_RESPONSE)
        response["Id"] = response["Id"].format(user_id=user_id)
        response["@odata.id"] = response["@odata.id"].format(user_id=user_id)
        response["UserName"] = username
        requests_mock.get(
            f"/redfish/v1/AccountService/Accounts/{user_id}", json=response, headers={"ETag": f"12345-{user_id}"}
        )


class RedfishTest(redfish.Redfish):
    """An inherited class used for testing."""

    @property
    def system_manager(self) -> str:
        """Property to return the System manager."""
        return "/redfish/v1/Systems/Testing_system.1"

    @property
    def oob_manager(self) -> str:
        """String representing the Out of Band manager key."""
        return "/redfish/v1/Managers/Testing_oob.1"

    @property
    def log_entries(self) -> str:
        """String representing the uri for the log entries."""
        return "/redfish/v1/Managers/Testing_oob.1/Logs"

    @property
    def reboot_message_id(self) -> str:
        """Property to return the Message Id for reboot log entries."""
        return "REBOOT_MSG_ID"


class TestRedfish:
    """Tests for the Redfish class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        interface = ipaddress.ip_interface("10.0.0.1/16")
        self.redfish = RedfishTest("test01", interface, "root", "mysecret", dry_run=False)
        self.redfish_dry_run = RedfishTest("test01", interface, "root", "mysecret", dry_run=True)
        self.requests_mock = requests_mock

    def test_property_magic_str(self):
        """It should equal the fqdn."""
        assert str(self.redfish) == "root@test01 (10.0.0.1)"

    def test_property_hostname(self):
        """It should equal the fqdn."""
        assert self.redfish.hostname == "test01"

    def test_property_interface(self):
        """It should equal the fqdn."""
        assert isinstance(self.redfish.interface, ipaddress.IPv4Interface)
        assert str(self.redfish.interface.ip) == "10.0.0.1"

    @pytest.mark.parametrize(
        "response, reboot_time",
        ((LCLOG_RESPONSE, "2022-06-22T16:42:55-05:00"), (LCLOG_RESPONSE_NO_MESSAGE, "1970-01-01T00:00:00-00:00")),
    )
    def test_last_reboot(self, response, reboot_time):
        """Return the last reboot time."""
        reboot_time = datetime.fromisoformat(reboot_time)
        self.requests_mock.get(self.redfish.log_entries, json=response)
        assert self.redfish.last_reboot() == reboot_time

    def test_wait_reboot_since(self):
        """It should raise an error if the reboot time is to early."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        self.requests_mock.get(self.redfish.log_entries, json=LCLOG_RESPONSE)
        since = datetime.fromisoformat("2022-01-01T00:05:00-00:00")
        self.redfish.wait_reboot_since(since)

    @mock.patch("spicerack.redfish.time.sleep")
    def test_wait_reboot_since_to_early(self, _mocked_sleep):
        """It should raise an error if the reboot time is to early."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        self.requests_mock.get(self.redfish.log_entries, json=LCLOG_RESPONSE_NO_MESSAGE)
        since = datetime.fromisoformat("2022-01-01T00:05:00-00:00")
        with pytest.raises(redfish.RedfishError, match="no new reboot detected"):
            self.redfish.wait_reboot_since(since)

    def test_property_system_info(self):
        """It should return the firmware."""
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        assert self.redfish.system_info == SYSTEM_MANAGER_RESPONSE
        # try again to hit the cached version
        assert self.redfish.system_info == SYSTEM_MANAGER_RESPONSE

    def test_property_updateservice_info(self):
        """It should return the firmware."""
        self.requests_mock.get(self.redfish.update_service, json=UPDATE_SERVICE_RESPONSE)
        assert self.redfish.updateservice_info == UPDATE_SERVICE_RESPONSE
        # try again to hit the cached version
        assert self.redfish.updateservice_info == UPDATE_SERVICE_RESPONSE

    def test_property_multipushuri(self):
        """It should return the multipushuri."""
        self.requests_mock.get(self.redfish.update_service, json=UPDATE_SERVICE_RESPONSE)
        assert self.redfish.multipushuri == "/redfish/v1/UpdateService/MultipartUpload"

    def test_property_bios(self):
        """It should return the firmware."""
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        assert self.redfish.bios_version == version.parse("2.15.1")

    def test_property_model(self):
        """It should return the firmware."""
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        assert self.redfish.model == "PowerEdge R440"

    def test_property_manufacturer(self):
        """It should return the firmware."""
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        assert self.redfish.manufacturer == "Dell Inc."

    def test_property_firmware(self):
        """It should return the firmware."""
        self.requests_mock.get(self.redfish.oob_manager, json=MANAGER_RESPONSE)
        assert self.redfish.firmware_version == version.parse("6.00.30.00")
        # assert twice to check cached version
        assert self.redfish.firmware_version == version.parse("6.00.30.00")

    def test_property_oob_model(self):
        """It should return the model."""
        self.requests_mock.get(self.redfish.oob_manager, json=MANAGER_RESPONSE)
        assert self.redfish.oob_model == "14G Monolithic"
        # assert twice to check cached version
        assert self.redfish.oob_model == "14G Monolithic"

    def test_property_missing_pushuri(self):
        """It should return the pushuri."""
        self.requests_mock.get(self.redfish.update_service, json=UPDATE_SERVICE_RESPONSE_NO_HTTP_PUSH)
        with pytest.raises(NotImplementedError):
            assert self.redfish.pushuri is None

    def test_most_recent_member(self):
        """It should return the item with the most recent date."""
        data = [
            {"date": "2022-01-01T00:00:00-00:00"},
            {"date": "1970-01-01T00:00:00-00:00"},
            {"date": "1971-01-01T00:00:00-00:00"},
        ]
        assert self.redfish.most_recent_member(data, "date") == {"date": "2022-01-01T00:00:00-00:00"}

    @pytest.mark.parametrize("method", ("get", "head"))
    def test_request_dry_run_ro(self, method):
        """It should perform any RO request and return the actual response also in dry_run mode."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        self.requests_mock.head("/redfish")
        response = self.redfish_dry_run.request(method, "/redfish")
        assert response.status_code == 200
        if method == "get":
            assert response.json() == {"v1": "/redfish/v1/"}

    @pytest.mark.parametrize("method", ("connect", "delete", "options", "patch", "post", "put", "trace"))
    def test_request_dry_run_rw(self, method):
        """It should not perform any RW request and return a dummy successful response in dry-run mode."""
        response = self.redfish_dry_run.request(method, "/redfish")
        assert response.status_code == 200
        assert not response.text

    def test_request_dry_run_fail(self, caplog):
        """If the request fails in dry-run mode, it should return a dummy successful response."""
        self.requests_mock.get("/redfish", exc=requests.exceptions.ConnectTimeout)
        with caplog.at_level(logging.ERROR):
            response = self.redfish_dry_run.request("get", "/redfish")

        assert response.status_code == 200
        assert "Failed to perform GET request to https://10.0.0.1/redfish" in caplog.text

    def test_request_ok(self):
        """It should perform the provided request and return it."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        response = self.redfish.request("get", "/redfish")
        assert response.json() == {"v1": "/redfish/v1/"}
        assert response.status_code == 200

    def test_request_response_wrong_status_code(self):
        """It should raise a RedfishError if the request returns an error status code."""
        self.requests_mock.post("/redfish", json={"error": {"code": "1.0", "message": "error"}}, status_code=405)
        with pytest.raises(redfish.RedfishError, match="POST https://10.0.0.1/redfish returned HTTP 405 with message"):
            self.redfish.request("post", "/redfish", json={"key": "value"})

    def test_request_response_raises(self):
        """It should raise a RedfishError if the request failes to be performed."""
        self.requests_mock.get("/redfish", exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(redfish.RedfishError, match="Failed to perform GET request to https://10.0.0.1/redfish"):
            self.redfish.request("get", "/redfish")

    def test_request_invalid_uri(self):
        """It should raise a RedfishError if the URI is invalid."""
        with pytest.raises(redfish.RedfishError, match="Invalid uri redfish, it must start with a /"):
            self.redfish.request("get", "redfish")

    def test_submit_task_dry_run(self):
        """In dry-run mode should not submit a task and return a dummy location."""
        assert self.redfish_dry_run.submit_task("/redfish/v1/SomeAction") == "/"

    def test_submit_task_ok(self):
        """It should submit the request and return the URI for polling the task results."""
        self.requests_mock.post(
            "/redfish/v1/SomeAction",
            status_code=202,
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
        )
        response = self.redfish.submit_task("/redfish/v1/SomeAction")
        assert response == "/redfish/v1/TaskService/Tasks/JID_1234567890"

    def test_submit_task_invalid_code(self):
        """It should raise a RedfishError if the status code is not 202."""
        self.requests_mock.post(
            "/redfish/v1/SomeAction",
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
        )
        with pytest.raises(redfish.RedfishError, match="expected HTTP 202, got HTTP 200 instead"):
            self.redfish.submit_task("/redfish/v1/SomeAction")

    def test_submit_task_no_location(self):
        """It should raise a RedfishError if there is no Location header in the response."""
        self.requests_mock.post("/redfish/v1/SomeAction", status_code=202)
        with pytest.raises(redfish.RedfishError, match="Unable to get the task URI to poll results"):
            self.redfish.submit_task("/redfish/v1/SomeAction")

    def test_connection_ok(self):
        """It should not raise if able to connect to the Redfish API."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        self.redfish.check_connection()

    def test_submit_task_file(self):
        """It should submit the request and return the URI for polling the task results."""
        self.requests_mock.get(self.redfish.update_service, json=UPDATE_SERVICE_RESPONSE)
        self.requests_mock.post(
            self.redfish.multipushuri,
            status_code=202,
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
        )
        assert self.redfish.submit_files({}) == "/redfish/v1/TaskService/Tasks/JID_1234567890"

    def test_submit_file_dry_run(self):
        """In dry-run mode should not submit a task and return a dummy location."""
        assert self.redfish_dry_run.submit_files({}) == "/"

    @mock.patch("spicerack.redfish.Path.open")
    @mock.patch("spicerack.redfish.Redfish.submit_files")
    def test_submit_upload_file(self, mock_submit_files, mocked_path_open):
        """In dry-run mode should not submit a task and return a dummy location."""
        mock_submit_files.return_value = "/redfish/v1/TaskService/Tasks/JID_1234567890"
        assert self.redfish.upload_file(Path("/foo/test")) == "/redfish/v1/TaskService/Tasks/JID_1234567890"
        mocked_path_open.called_once_with("rb")

    @pytest.mark.parametrize("reboot", (True, False))
    @mock.patch("spicerack.redfish.Redfish.submit_files")
    def test_submit_multipush_upload(self, mock_submit_files, reboot):
        """In dry-run mode should not submit a task and return a dummy location."""
        mock_submit_files.return_value = "/redfish/v1/TaskService/Tasks/JID_1234567890"
        data = BytesIO()
        assert self.redfish.multipush_upload("test", data, reboot) == "/redfish/v1/TaskService/Tasks/JID_1234567890"

    def test_connection_fail(self):
        """It should raise a RedfishError if unable to connect to the Redfish API."""
        self.requests_mock.get("/redfish", status_code=400)
        with pytest.raises(redfish.RedfishError, match="GET https://10.0.0.1/redfish returned HTTP 400"):
            self.redfish.check_connection()

    def test_poll_task_dry_run(self):
        """It should return a dummy response in dry-run mode."""
        assert self.redfish_dry_run.poll_task("/redfish/v1/TaskService/Tasks/JID_1234567890") == {}

    @pytest.mark.parametrize("response", (DELL_TASK_REPONSE, DELL_TASK_REPONSE_EPOC, DELL_TASK_REPONSE_BAD_TIME))
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_poll_endtime(self, mocked_sleep, response):
        """It should raise a RedfishError if polling the task the device returns a failure code."""
        self.requests_mock.get("/redfish/v1/TaskService/Tasks/JID_1234567890", status_code=202, json=response)
        with pytest.raises(redfish.RedfishTaskNotCompletedError):
            self.redfish.poll_task("/redfish/v1/TaskService/Tasks/JID_1234567890")
        mocked_sleep.assert_called()

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_poll_task_raises(self, mocked_sleep):
        """It should raise a RedfishError if polling the task the device returns a failure code."""
        self.requests_mock.get("/redfish/v1/TaskService/Tasks/JID_1234567890", status_code=201)
        with pytest.raises(redfish.RedfishError, match="JID_1234567890 returned HTTP 201"):
            self.redfish.poll_task("/redfish/v1/TaskService/Tasks/JID_1234567890")

        mocked_sleep.assert_not_called()

    def test_find_account_ok(self):
        """It should return the URI of the account with the given username."""
        add_accounts_mock_responses(self.requests_mock)
        uri, etag = self.redfish.find_account("root")
        assert uri == "/redfish/v1/AccountService/Accounts/2"
        assert etag == "12345-2"

    def test_find_account_raises(self):
        """It should raise a RedfishError if the user is not found."""
        add_accounts_mock_responses(self.requests_mock)
        with pytest.raises(redfish.RedfishError, match="Unable to find account for username nonexistent"):
            self.redfish.find_account("nonexistent")

    @pytest.mark.parametrize("user_id, username, is_current", ((1, "user", False), (2, "root", True)))
    def test_change_user_password_ok(self, user_id, username, is_current):
        """It should change the password for the given user and update the instance auth credentials accordingly."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        add_accounts_mock_responses(self.requests_mock)
        response = {
            "@Message.ExtendedInfo": [
                {"Message": "Changed password", "MessageId": "123", "Severity": "Informational", "Resolution": "None"}
            ]
        }
        self.requests_mock.patch(f"/redfish/v1/AccountService/Accounts/{user_id}", json=response)

        current_auth = self.redfish.request("get", "/redfish").request.headers["Authorization"]
        self.redfish.change_user_password(username, "test1234")
        new_auth = self.redfish.request("get", "/redfish").request.headers["Authorization"]

        if is_current:  # Check that the authorization header changed
            assert new_auth != current_auth
        else:
            assert new_auth == current_auth

    def test_change_user_password_raises(self):
        """It should raise a RedfishError if the reponse is not what HTTP 200."""
        add_accounts_mock_responses(self.requests_mock)
        self.requests_mock.patch("/redfish/v1/AccountService/Accounts/2", status_code=202)
        with pytest.raises(redfish.RedfishError, match="Got unexpected HTTP 202, expected 200"):
            self.redfish.change_user_password("root", "test1234")

    def test_get_power_state(self):
        """It should return the current power state of the device."""
        self.requests_mock.get("/redfish/v1/Chassis/System.Embedded.1", json={"PowerState": "On"})
        assert self.redfish.get_power_state() == "On"

    @pytest.mark.parametrize("action", tuple(redfish.ChassisResetPolicy))
    def test_chassis_reset_ok(self, action):
        """It should perform a chassis reset with the given action."""
        self.requests_mock.post("/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset", status_code=204)
        self.redfish.chassis_reset(action)

    def test_chassis_reset_raises(self):
        """It should raise a RedfishError if the response code of the chassis reset operation is not 204."""
        self.requests_mock.post("/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset")
        with pytest.raises(redfish.RedfishError, match="Got unexpected response HTTP 200, expected HTTP 204"):
            self.redfish.chassis_reset(redfish.ChassisResetPolicy.FORCE_OFF)


class TestDellSCP:
    """Tests for the DellSCP class."""

    def setup_method(self):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.config = redfish.DellSCP(deepcopy(DELL_SCP), redfish.DellSCPTargetPolicy.ALL)
        self.config_allow_new = redfish.DellSCP(
            deepcopy(DELL_SCP), redfish.DellSCPTargetPolicy.ALL, allow_new_attributes=True
        )

    @pytest.mark.parametrize(
        "property_name, expected",
        (
            ("config", DELL_SCP),
            ("target", redfish.DellSCPTargetPolicy.ALL),
            ("service_tag", "12ABC34"),
            ("model", "PowerEdge R440"),
            ("timestamp", datetime(2021, 12, 9, 9, 32, 6)),
            ("comments", ["First comment"]),
            (
                "components",
                {
                    "Some.Component.1": {"Some.Attribute.1": "value"},
                    "Some.Component.2": {"Some.Attribute.1": "value", "Some.Attribute.2": "value"},
                    "List.Component.1": {
                        "Comma.Separated.List.1": "value1,value2",
                        "Comma.Space.Separated.List.1": "value1, value2",
                    },
                },
            ),
        ),
    )
    def test_properties(self, property_name, expected):
        """It should return the value of the given property."""
        assert getattr(self.config, property_name) == expected
        assert getattr(self.config_allow_new, property_name) == expected

    @pytest.mark.parametrize(
        "component, attribute, exception_message",
        (
            ("Non.Existent", "Some.Attribute.1", "Unable to find component Non.Existent"),
            ("Some.Component.1", "Non.Existent", "Unable to find attribute Some.Component.1 -> Non.Existent"),
        ),
    )
    def test_set_raise(self, component, attribute, exception_message):
        """It should raise RedfishError if the specified component or attribute does not exists and is now allowed."""
        with pytest.raises(redfish.RedfishError, match=exception_message):
            self.config.set(component, attribute, "new_value")

    def test_set_new_attribute(self):
        """It should add the new attribute if allow_new_attributes is set to True or empty_components() was called."""
        params = ["Some.Component.1", "Non.Existent", "new_value"]
        self.config_allow_new.set(*params)
        assert self.config_allow_new.components[params[0]][params[1]] == params[2]
        self.config.empty_components()
        self.config.set(*params)
        assert self.config.components[params[0]][params[1]] == params[2]

    def test_set_raise_new_component(self):
        """It should raise RedfishError if the component does not exists even if allow_new_attributes is set."""
        with pytest.raises(redfish.RedfishError, match="Unable to find component Non.Existent"):
            self.config_allow_new.set("Non.Existent", "Some.Attribute.1", "new_value")

    def test_set_new_component(self):
        """It should create a new component and add to it the new attribute if empty_components() was called."""
        self.config.empty_components()
        self.config.set("Non.Existent", "Some.Attribute.1", "new_value")
        assert self.config.components["Non.Existent"]["Some.Attribute.1"] == "new_value"

    @pytest.mark.parametrize(
        "index, component, attribute, value",
        (
            (1, "Some.Component.1", "Some.Attribute.1", "value"),
            (2, "List.Component.1", "Comma.Separated.List.1", "value1,value2"),
            (2, "List.Component.1", "Comma.Space.Separated.List.1", "value1, value2"),
        ),
    )
    def test_set_same_value(self, index, component, attribute, value, caplog):
        """It should not set the same value and log a different message if the value is already correct."""
        with caplog.at_level(logging.INFO):
            was_changed = self.config.set(component, attribute, value)

        assert not was_changed
        assert f"Skipped set of attribute {component} -> {attribute}, has already" in caplog.text
        assert all(
            i["Set On Import"] == "False"
            for i in self.config.config["SystemConfiguration"]["Components"][index]["Attributes"]
        )

    def test_set_new_value(self):
        """It should set the value and mark it for import."""
        was_changed = self.config.set("Some.Component.1", "Some.Attribute.1", "new value")
        attribute = self.config.config["SystemConfiguration"]["Components"][1]["Attributes"][0]
        assert was_changed
        assert attribute["Value"] == "new value"
        assert attribute["Set On Import"] == "True"

    def test_update(self):
        """It should update the config with the given changes."""
        changes = {
            "Some.Component.1": {"Some.Attribute.1": "value"},
            "Some.Component.2": {"Some.Attribute.2": "new value"},
        }
        was_changed = self.config.update(changes)
        assert was_changed
        assert self.config.components["Some.Component.1"]["Some.Attribute.1"] == "value"
        assert self.config.components["Some.Component.2"]["Some.Attribute.2"] == "new value"

    def test_update_no_changes(self):
        """It should return False if no changes were made."""
        changes = {
            "Some.Component.1": {"Some.Attribute.1": "value"},
            "Some.Component.2": {"Some.Attribute.2": "value"},
        }
        was_changed = self.config.update(changes)
        assert not was_changed
        assert self.config.components["Some.Component.1"]["Some.Attribute.1"] == "value"
        assert self.config.components["Some.Component.2"]["Some.Attribute.2"] == "value"

    def test_empty_components(self):
        """It should empty the components of the current configuration."""
        self.config.empty_components()
        assert self.config.components == {}


class TestRedfishDell:
    """Tests for the RedfishDell class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        interface = ipaddress.ip_interface("10.0.0.1/16")
        self.redfish = redfish.RedfishDell("test01", interface, "root", "mysecret", dry_run=False)
        self.requests_mock = requests_mock

    def test_property_system_manager(self):
        """It should return the oob_manager."""
        assert self.redfish.system_manager == "/redfish/v1/Systems/System.Embedded.1"

    def test_property_oob_manager(self):
        """It should return the oob_manager."""
        assert self.redfish.oob_manager == "/redfish/v1/Managers/iDRAC.Embedded.1"

    @pytest.mark.parametrize(
        "response, endpoint",
        (
            (MANAGER_RESPONSE, "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries"),
            (MANAGER_RESPONSE_V3, "/redfish/v1/Managers/Logs/Lclog"),
        ),
    )
    def test_property_log_entries(self, response, endpoint) -> str:
        """String representing the uri for the log entries."""
        self.requests_mock.get(self.redfish.oob_manager, json=response)
        assert self.redfish.log_entries == endpoint

    def test_property_reboot_message_id(self) -> str:
        """Property to return the Message Id for reboot log entries."""
        assert self.redfish.reboot_message_id == "RAC0182"

    @pytest.mark.parametrize("response, generation", ((MANAGER_RESPONSE, 14), (MANAGER_RESPONSE_BAD, 1)))
    def test_property_generation(self, response, generation):
        """It should return the generation."""
        self.requests_mock.get(self.redfish.oob_manager, json=response)
        assert self.redfish.generation == generation
        # assert twice to check cached version
        assert self.redfish.generation == generation

    @pytest.mark.parametrize("generation", (1, 13, 14))
    @mock.patch("spicerack.redfish.time.sleep")
    @mock.patch("spicerack.redfish.RedfishDell.last_reboot")
    @mock.patch("spicerack.redfish.RedfishDell.check_connection")
    def test_wait_reboot_since(self, mocked_check_connection, mocked_last_reboot, mocked_sleep, generation):
        """It should return immediately if the host has already rebooted."""
        since = datetime.fromisoformat("2022-01-01T00:00:00-00:00")
        mocked_check_connection.return_value = True
        mocked_last_reboot.return_value = datetime.fromisoformat("2022-01-01T00:05:00-00:00")
        self.redfish._generation = generation  # pylint: disable=protected-access
        self.redfish.wait_reboot_since(since)
        mocked_check_connection.called_once()
        mocked_last_reboot.called_once_with(since)
        if generation < 14:
            mocked_sleep.called_once_with(120)
        mocked_sleep.called_once_with(30)

    @pytest.mark.parametrize("generation", (1, 13, 14))
    @mock.patch("spicerack.redfish.time.sleep")
    @mock.patch("spicerack.redfish.RedfishDell.last_reboot")
    @mock.patch("spicerack.redfish.RedfishDell.check_connection")
    def test_wait_reboot_since_to_early(self, mocked_check_connection, mocked_last_reboot, mocked_sleep, generation):
        """It should raise an error if the reboot time is to early."""
        since = datetime.fromisoformat("2022-01-01T00:05:00-00:00")
        mocked_check_connection.return_value = True
        mocked_last_reboot.return_value = datetime.fromisoformat("2022-01-01T00:00:00-00:00")
        self.redfish._generation = generation  # pylint: disable=protected-access
        with pytest.raises(redfish.RedfishError, match="no new reboot detected"):
            self.redfish.wait_reboot_since(since)
        mocked_check_connection.called_once()
        mocked_last_reboot.called_once_with(since)
        if generation < 14:
            mocked_sleep.called_once_with(120)

    @pytest.mark.parametrize("allow_new", (False, True))
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_scp_dump(self, mocked_sleep, allow_new):
        """It should return an instance of DellSCP with the current configuration for the given target."""
        self.requests_mock.post(
            "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/EID_674_Manager.ExportSystemConfiguration",
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
            status_code=202,
        )
        self.requests_mock.get(
            "/redfish/v1/TaskService/Tasks/JID_1234567890",
            [{"status_code": 202, "json": DELL_TASK_REPONSE}, {"status_code": 200, "json": DELL_SCP}],
        )
        config = self.redfish.scp_dump(allow_new_attributes=allow_new)
        assert config.service_tag == "12ABC34"
        assert mocked_sleep.called
        if allow_new:
            config.set("Some.Component.1", "Non.Existent", "new_value")
            assert config.components["Some.Component.1"]["Non.Existent"] == "new_value"
        else:
            with pytest.raises(redfish.RedfishError, match="Unable to find attribute Some.Component.1 -> Non.Existent"):
                config.set("Some.Component.1", "Non.Existent", "new_value")

    @pytest.mark.parametrize(
        "uri_suffix, preview",
        (
            ("ImportSystemConfigurationPreview", True),
            ("ImportSystemConfiguration", False),
        ),
    )
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_scp_push(self, mocked_sleep, uri_suffix, preview):
        """It should push the configuration to the device for preview, no changes will be applied."""
        expected = deepcopy(DELL_TASK_REPONSE)
        expected["EndTime"] = "2021-12-09T14:39:29-06:00"
        self.requests_mock.post(
            f"/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/EID_674_Manager.{uri_suffix}",
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
            status_code=202,
        )
        self.requests_mock.get(
            "/redfish/v1/TaskService/Tasks/JID_1234567890",
            [{"status_code": 202, "json": DELL_TASK_REPONSE}, {"status_code": 200, "json": expected}],
        )
        result = self.redfish.scp_push(redfish.DellSCP(DELL_SCP, redfish.DellSCPTargetPolicy.ALL), preview=preview)
        assert result == expected
        assert mocked_sleep.called


class TestRedfishSupermicro:
    """Tests for the RedfishSupermicro class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        interface = ipaddress.ip_interface("10.0.0.1/16")
        self.redfish = redfish.RedfishSupermicro("test01", interface, "root", "mysecret", dry_run=False)
        self.requests_mock = requests_mock

    def test_property_system_manager(self):
        """It should return the oob_manager."""
        assert self.redfish.system_manager == "/redfish/v1/Systems/1"

    def test_property_oob_manager(self):
        """It should return the oob_manager."""
        assert self.redfish.oob_manager == "/redfish/v1/Managers/1"

    def test_property_log_entries(self) -> str:
        """String representing the uri for the log entries."""
        assert self.redfish.log_entries == "/redfish/v1/Managers/1/LogServices/Log1/Entries"

    def test_property_reboot_message_id(self) -> str:
        """Property to return the Message Id for reboot log entries."""
        assert self.redfish.reboot_message_id == "Event.1.0.SystemPowerAction"
