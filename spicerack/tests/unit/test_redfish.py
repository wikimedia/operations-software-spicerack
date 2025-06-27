"""Redfish module tests."""

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
ADD_ACCOUNT_RESPONSE = {
    "@odata.id": "/redfish/v1/AccountService/Accounts/42",
    "@odata.type": "#ManagerAccount.v1_8_0.ManagerAccount",
    "AccountTypes": ["Redfish"],
    "Description": "User Account",
    "Enabled": True,
    "HostBootstrapAccount": False,
    "Id": "42",
    "Links": {"Role": {"@odata.id": "/redfish/v1/AccountService/Roles/Administrator"}},
    "Locked": False,
    "Name": "User Account",
    "Password": None,
    "RoleId": "Administrator",
    "UserName": "{username}",
}
ADD_ACCOUNT_RESPONSE_DUPLICATED_USER = {
    "error": {
        "code": "Base.v1_10_3.GeneralError",
        "message": "A general error has occurred. See ExtendedInfo for more information.",
        "@Message.ExtendedInfo": [
            {
                "MessageId": "Base.1.10.ActionParameterDuplicate",
                "Severity": "Warning",
                "Resolution": "Resubmit the action with only one instance of the parameter "
                "in the request body if the operation failed.",
                "Message": "The action batman was submitted with more than one value " "for the parameter UserName.",
                "MessageArgs": ["{username}", "UserName"],
                "RelatedProperties": ["{username}", "UserName"],
            }
        ],
    }
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


def get_scp_dell_nics(nic2, nic3):
    """Get the NIC components of a system configuration based on parameters."""
    return {
        "SystemConfiguration": {
            "Components": [
                {
                    "FQDD": "NIC.Embedded.1-1-1",
                    "Attributes": [
                        {"Name": "LegacyBootProto", "Value": "NONE"},
                    ],
                },
                {
                    "FQDD": "NIC.Embedded.2-1-1",
                    "Attributes": [
                        {"Name": "LegacyBootProto", "Value": nic2},
                    ],
                },
                {
                    "FQDD": "NIC.Integrated.1-1-1",
                    "Attributes": [
                        {"Name": "LegacyBootProto", "Value": nic3},
                    ],
                },
                {
                    "FQDD": "NIC.Integrated.1-2-1",
                    "Attributes": [
                        {"Name": "LegacyBootProto", "Value": "NONE"},
                    ],
                },
            ],
        },
    }


def add_accounts_mock_responses(requests_mock):
    """Setup requests mock URLs and return payloads for all the existing users."""
    requests_mock.get("/redfish/v1/AccountService/Accounts", json=ACCOUNTS_RESPONSE)
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

    system = "Testing_system.1"
    manager = "Testing_oob.1"
    log_service = "Testing_oob.1"
    reboot_message_id = "REBOOT_MSG_ID"
    boot_mode_attribute = "BootMode"
    http_boot_target = "UefiHttp"

    def get_power_state(self) -> str:
        """Return the current power state of the device."""
        return "On"


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

    def test_property_uuid(self):
        """It should return the UUID."""
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        assert self.redfish.uuid == "4c4c4544-0058-3810-8032-b2c04f525032"

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

    def test_request_response_wrong_status_code(self):
        """It should raise a RedfishError if the request returns an error status code."""
        self.requests_mock.post("/redfish", json={"error": {"code": "1.0", "message": "error"}}, status_code=405)
        with pytest.raises(redfish.RedfishError, match="POST https://10.0.0.1/redfish returned HTTP 405"):
            self.redfish.request("post", "/redfish", json={"key": "value"})

    def test_request_response_wrong_status_code_invalid_json(self):
        """It should raise a RedfishError if the request returns an error status code and the response is not JSON."""
        self.requests_mock.post("/redfish", json="this is not valid", status_code=405)
        with pytest.raises(redfish.RedfishError, match="POST https://10.0.0.1/redfish returned HTTP 405"):
            self.redfish.request("post", "/redfish", json={"key": "value"})

    def test_request_response_raises(self):
        """It should raise a RedfishError if the request failes to be performed."""
        self.requests_mock.get("/redfish", exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(redfish.RedfishError, match="Failed to perform GET request to https://10.0.0.1/redfish"):
            self.redfish.request("get", "/redfish")

    def test_request_invalid_uri(self):
        """It should raise a RedfishError if the URI is invalid."""
        with pytest.raises(redfish.RedfishError, match="Invalid uri 'redfish', it must start with a /"):
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
        mocked_path_open.assert_called_once_with("rb")

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

    @pytest.mark.parametrize(
        "response, password",
        (
            (
                {
                    "@Message.ExtendedInfo": [
                        {
                            "Message": "Changed password",
                            "MessageId": "123",
                            "Severity": "Informational",
                            "Resolution": "None",
                        }
                    ]
                },
                "test1234",
            ),
            (None, "test12345"),
        ),
    )
    @pytest.mark.parametrize("user_id, username, is_current", ((1, "user", False), (2, "root", True)))
    def test_change_user_password_ok(self, user_id, username, is_current, response, password):
        """It should change the password for the given user and update the instance auth credentials accordingly."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        add_accounts_mock_responses(self.requests_mock)
        self.requests_mock.patch(f"/redfish/v1/AccountService/Accounts/{user_id}", json=response)

        current_auth = self.redfish.request("get", "/redfish").request.headers["Authorization"]
        self.redfish.change_user_password(username, password)
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

    @pytest.mark.parametrize("action", tuple(redfish.ChassisResetPolicy))
    def test_chassis_reset_ok(self, action):
        """It should perform a chassis reset with the given action."""
        self.requests_mock.post("/redfish/v1/Systems/Testing_system.1/Actions/ComputerSystem.Reset", status_code=204)
        self.redfish.chassis_reset(action)

    def test_chassis_reset_raises(self):
        """It should raise a RedfishError if the response code of the chassis reset operation is not 200/204."""
        self.requests_mock.post("/redfish/v1/Systems/Testing_system.1/Actions/ComputerSystem.Reset", status_code=201)
        with pytest.raises(redfish.RedfishError, match="Got unexpected response HTTP 201, expected HTTP 200/204"):
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

    def test_property_storage_manager(self):
        """It should return the storage_manager."""
        assert self.redfish.storage_manager == "/redfish/v1/Systems/System.Embedded.1/Storage"

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
        mocked_check_connection.assert_called_once()
        mocked_last_reboot.assert_called_once_with()
        calls = []
        if generation < 14:
            calls.append(mock.call(120))
        calls.append(mock.call(30))
        assert mocked_sleep.mock_calls == calls

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
        mocked_check_connection.assert_called_with()
        assert mocked_check_connection.call_count == 240
        mocked_last_reboot.assert_called_with()
        assert mocked_last_reboot.call_count == 240
        calls = []
        if generation < 14:
            calls = [mock.call(120), mock.call(10)] * 239 + [mock.call(120)]
        else:
            calls = [mock.call(10)] * 239

        assert mocked_sleep.mock_calls == calls

    @pytest.mark.parametrize(
        "model, expected_params",
        (("16G Monolithic", {"Target": "ALL"}), ("17G Monolithic", {"Target": ["ALL"]})),
    )
    @pytest.mark.parametrize("allow_new", (False, True))
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_scp_dump(self, mocked_sleep, allow_new, model, expected_params):
        """It should return an instance of DellSCP with the current configuration for the given target."""
        self.requests_mock.get("/redfish/v1/Managers/iDRAC.Embedded.1", json={"Model": model})
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
        assert self.requests_mock.request_history[1].json()["ShareParameters"] == expected_params

        if allow_new:
            config.set("Some.Component.1", "Non.Existent", "new_value")
            assert config.components["Some.Component.1"]["Non.Existent"] == "new_value"
        else:
            with pytest.raises(redfish.RedfishError, match="Unable to find attribute Some.Component.1 -> Non.Existent"):
                config.set("Some.Component.1", "Non.Existent", "new_value")

    @pytest.mark.parametrize(
        "model, expected_params",
        (("16G Monolithic", {"Target": "ALL"}), ("17G Monolithic", {"Target": ["ALL"]})),
    )
    @pytest.mark.parametrize(
        "uri_suffix, preview",
        (
            ("ImportSystemConfigurationPreview", True),
            ("ImportSystemConfiguration", False),
        ),
    )
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_scp_push(self, mocked_sleep, uri_suffix, preview, model, expected_params):
        """It should push the configuration to the device for preview, no changes will be applied."""
        expected = deepcopy(DELL_TASK_REPONSE)
        expected["EndTime"] = "2021-12-09T14:39:29-06:00"
        self.requests_mock.get("/redfish/v1/Managers/iDRAC.Embedded.1", json={"Model": model})
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
        assert self.requests_mock.request_history[1].json()["ShareParameters"] == expected_params

    def test_get_power_state(self):
        """It should return the current power state of the device."""
        self.requests_mock.get("/redfish/v1/Chassis/System.Embedded.1", json={"PowerState": "On"})
        assert self.redfish.get_power_state() == "On"

    def test_property_boot_mode_attribute(self):
        """Property to return the boot mode key in the Bios attributes."""
        assert self.redfish.boot_mode_attribute == "BootMode"

    def test_is_uefi(self):
        """It should return that the device is not UEFI."""
        self.requests_mock.get(
            "/redfish/v1/Systems/System.Embedded.1/Bios", json={"Attributes": {"BootMode": "Legacy"}}
        )
        assert self.redfish.is_uefi is False

    @mock.patch("wmflib.decorators.time.sleep")
    def test_get_primary_mac(self, _mocked_sleep):
        """It should return the pxe enabled mac."""
        self.requests_mock.post(
            "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/EID_674_Manager.ExportSystemConfiguration",
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
            status_code=202,
        )
        scp = get_scp_dell_nics("NONE", "PXE")
        self.requests_mock.get(
            "/redfish/v1/TaskService/Tasks/JID_1234567890",
            [{"status_code": 202, "json": DELL_TASK_REPONSE}, {"status_code": 200, "json": scp}],
        )
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        self.requests_mock.get(self.redfish.oob_manager, json=MANAGER_RESPONSE)
        ifaces = {
            "@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces",
            "Members": [
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Embedded.1-1-1"},
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Embedded.2-1-1"},
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-1-1"},
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-2-1"},
            ],
        }
        self.requests_mock.get("/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces", json=ifaces)

        iface = {
            "@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-1-1",
            "MACAddress": "00:62:0B:C8:9C:50",
        }
        self.requests_mock.get(
            "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-1-1",
            json=iface,
        )
        assert self.redfish.get_primary_mac() == "00:62:0b:c8:9c:50"

    @pytest.mark.parametrize(
        "idrac_gen, redfish_uri",
        ((14, "/redfish/v1/Systems/System.Embedded.1"), (17, "/redfish/v1/Systems/System.Embedded.1/Settings")),
    )
    def test_force_http_boot_once_ok(self, idrac_gen: int, redfish_uri: str):
        """It should change the HTTP boot mode."""
        self.requests_mock.get("/redfish/v1/Systems/System.Embedded.1/Bios", json={"Attributes": {"BootMode": "UEFI"}})
        self.requests_mock.patch(redfish_uri, status_code=204)
        self.redfish._generation = idrac_gen  # pylint: disable=protected-access
        self.redfish.force_http_boot_once()
        assert self.requests_mock.last_request.method == "PATCH"
        request_json = self.requests_mock.last_request.json()
        request_json_to_match = {
            "Boot": {
                "BootSourceOverrideEnabled": "Once",
                "BootSourceOverrideTarget": "UefiHttp",
            }
        }
        if idrac_gen < self.redfish.idrac_10_min_gen:
            request_json_to_match["Boot"]["BootSourceOverrideMode"] = "UEFI"
        assert request_json == request_json_to_match

    def test_force_http_boot_once_raise(self):
        """It should raise a RedfishError as the BootMode is not UEFI."""
        self.requests_mock.get(
            "/redfish/v1/Systems/System.Embedded.1/Bios", json={"Attributes": {"BootMode": "Legacy"}}
        )
        with pytest.raises(redfish.RedfishError, match="HTTP boot is only possible for UEFI hosts."):
            self.redfish.force_http_boot_once()

    @pytest.mark.parametrize(
        "nic_pxe, nic_name, error_msg",
        (
            ({"nic2": "PXE", "nic3": "PXE"}, "", "Found more than 1 NIC with PXE enabled: "),
            ({"nic2": "NONE", "nic3": "NONE"}, "", "No PXE enabled NIC found"),
            ({"nic2": "NONE", "nic3": "PXE"}, "foobar", "No MAC found on the PXE enabled interface"),
        ),
    )
    @mock.patch("wmflib.decorators.time.sleep")
    def test_get_primary_mac_error(self, _mocked_sleep, nic_pxe, nic_name, error_msg):
        """It should raise an error if there is none or more than 1 PXE nic."""
        self.requests_mock.post(
            "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/EID_674_Manager.ExportSystemConfiguration",
            headers={"Location": "/redfish/v1/TaskService/Tasks/JID_1234567890"},
            status_code=202,
        )
        scp = get_scp_dell_nics(nic_pxe["nic2"], nic_pxe["nic3"])

        self.requests_mock.get(
            "/redfish/v1/TaskService/Tasks/JID_1234567890",
            [{"status_code": 202, "json": DELL_TASK_REPONSE}, {"status_code": 200, "json": scp}],
        )
        self.requests_mock.get(self.redfish.system_manager, json=SYSTEM_MANAGER_RESPONSE)
        self.requests_mock.get(self.redfish.oob_manager, json=MANAGER_RESPONSE)
        ifaces = {
            "@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces",
            "Members": [
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Embedded.1-1-1"},
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Embedded.2-1-1"},
                {"@odata.id": f"/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/{nic_name}"},
                {"@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-2-1"},
            ],
        }
        self.requests_mock.get("/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces", json=ifaces)

        iface = {
            "@odata.id": "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-1-1",
            "MACAddress": "00:62:0B:C8:9C:50",
        }
        self.requests_mock.get(
            "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/NIC.Integrated.1-1-1",
            json=iface,
        )
        with pytest.raises(redfish.RedfishError, match=error_msg):
            self.redfish.get_primary_mac()


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

    def test_property_storage_manager(self):
        """It should return the storage_manager."""
        assert self.redfish.storage_manager == "/redfish/v1/Systems/1/Storage"

    def test_property_log_entries(self) -> str:
        """String representing the uri for the log entries."""
        assert self.redfish.log_entries == "/redfish/v1/Managers/1/LogServices/Log1/Entries"

    def test_property_reboot_message_id(self) -> str:
        """Property to return the Message Id for reboot log entries."""
        assert self.redfish.reboot_message_id == "Event.1.0.SystemPowerAction"

    def test_get_power_state(self):
        """It should return the current power state of the device."""
        self.requests_mock.get("/redfish/v1/Systems/1", json={"PowerState": "On"})
        assert self.redfish.get_power_state() == "On"

    @pytest.mark.parametrize(
        "username, password, role",
        (
            ("batman", "12345", redfish.RedfishUserRoles.ADMINISTRATOR),
            ("batman", "12345", redfish.RedfishUserRoles.OPERATOR),
            ("batman", "12345", redfish.RedfishUserRoles.READONLY),
        ),
    )
    def test_add_account(self, username, password, role):
        """It should create the new user."""
        response = deepcopy(ADD_ACCOUNT_RESPONSE)
        response["UserName"] = response["UserName"].format(username=username)
        self.requests_mock.post("/redfish/v1/AccountService/Accounts", json=response, status_code=201)
        self.redfish.add_account(username, password, role)

    def test_add_account_raises(self):
        """It should raise a RedfishError if the reponse is not HTTP 20X."""
        response = deepcopy(ADD_ACCOUNT_RESPONSE_DUPLICATED_USER)
        response["error"]["@Message.ExtendedInfo"][0]["MessageArgs"][0] = response["error"]["@Message.ExtendedInfo"][0][
            "MessageArgs"
        ][0].format(username="batman")
        response["error"]["@Message.ExtendedInfo"][0]["RelatedProperties"][0] = response["error"][
            "@Message.ExtendedInfo"
        ][0]["RelatedProperties"][0].format(username="batman")
        self.requests_mock.post("/redfish/v1/AccountService/Accounts", json=response, status_code=500)
        with pytest.raises(
            redfish.RedfishError, match="POST https://10.0.0.1/redfish/v1/AccountService/Accounts returned HTTP 500"
        ):
            self.redfish.add_account("batman", "12345")

    def test_property_boot_mode_attribute(self) -> str:
        """Property to return the boot mode key in the Bios attributes."""
        assert self.redfish.boot_mode_attribute == "BootModeSelect"

    def test_is_uefi(self):
        """It should return the device is UEFI."""
        self.requests_mock.get("/redfish/v1/Systems/1/Bios", json={"Attributes": {"BootModeSelect": "UEFI"}})
        assert self.redfish.is_uefi is True

    def test_get_primary_mac(self):
        """It should return the pxe enabled mac."""
        bios = {
            "@odata.id": "/redfish/v1/Systems/1/Bios",
            "Attributes": {"OnboardLAN1OptionROM": "EFI"},
        }
        self.requests_mock.get("/redfish/v1/Systems/1/Bios", json=bios)

        adapters = {
            "@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters",
            "Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1"}],
        }
        self.requests_mock.get("/redfish/v1/Chassis/1/NetworkAdapters", json=adapters)

        adapter = {
            "@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1",
            "Controllers": [
                {
                    "Links": {
                        "Ports": [
                            {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/Ports/1"},
                            {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/Ports/2"},
                        ]
                    }
                }
            ],
            "Model": "AOC-S25G-b2S",
        }
        self.requests_mock.get("/redfish/v1/Chassis/1/NetworkAdapters/1", json=adapter)

        port = {
            "@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/Ports/1",
            "Ethernet": {"AssociatedMACAddresses": ["7C:C2:55:97:5A:0E"]},
        }
        self.requests_mock.get("/redfish/v1/Chassis/1/NetworkAdapters/1/Ports/1", json=port)
        assert self.redfish.get_primary_mac() == "7c:c2:55:97:5a:0e"

    def test_force_http_boot_once_ok(self):
        """It should change the HTTP boot mode."""
        self.requests_mock.get("/redfish/v1/Systems/1/Bios", json={"Attributes": {"BootModeSelect": "UEFI"}})
        self.requests_mock.patch("/redfish/v1/Systems/1", status_code=204)
        self.redfish.force_http_boot_once()
        assert self.requests_mock.last_request.method == "PATCH"
        request_json = self.requests_mock.last_request.json()
        assert request_json == {
            "Boot": {
                "BootSourceOverrideEnabled": "Once",
                "BootSourceOverrideTarget": "Pxe",
                "BootSourceOverrideMode": "UEFI",
            }
        }

    def test_force_http_boot_once_raise(self):
        """It should raise a RedfishError as the BootMode is not UEFI."""
        self.requests_mock.get("/redfish/v1/Systems/1/Bios", json={"Attributes": {"BootMode": "Legacy"}})
        with pytest.raises(redfish.RedfishError, match="HTTP boot is only possible for UEFI hosts."):
            self.redfish.force_http_boot_once()

    @pytest.mark.parametrize(
        "bios_attributes, error_msg",
        (
            (
                {"OnboardLAN1OptionROM": "EFI", "OnboardLAN2OptionROM": "EFI"},
                "Found more than 1 NIC with PXE enabled: ",
            ),
            ({}, "No PXE enabled NIC found"),
            ({"OnboardLAN1OptionROM": "EFI"}, "No MAC found on the PXE enabled interface"),
        ),
    )
    def test_get_primary_mac_error(self, bios_attributes, error_msg):
        """It should raise an error if there is none or more than 1 PXE nic."""
        bios = {
            "@odata.id": "/redfish/v1/Systems/1/Bios",
            "Attributes": bios_attributes,
        }
        self.requests_mock.get("/redfish/v1/Systems/1/Bios", json=bios)

        adapters = {
            "@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters",
            "Members": [],
        }
        self.requests_mock.get("/redfish/v1/Chassis/1/NetworkAdapters", json=adapters)

        with pytest.raises(redfish.RedfishError, match=error_msg):
            self.redfish.get_primary_mac()
