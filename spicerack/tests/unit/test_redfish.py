"""Netbox module tests."""
import logging
from copy import deepcopy
from datetime import datetime
from unittest import mock

import pytest
import requests

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
MODEL_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#Manager.Manager",
    "@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1",
    "@odata.type": "#Manager.v1_9_0.Manager",
    "Model": "14G Monolithic",
}
MODEL_RESPONSE_BAD = deepcopy(MODEL_RESPONSE)
MODEL_RESPONSE_BAD["Model"] = "Foobar"
PUSHURI_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#UpdateService.UpdateService",
    "@odata.id": "/redfish/v1/UpdateService",
    "@odata.type": "#UpdateService.v1_8_1.UpdateService",
    "HttpPushUri": "/redfish/v1/UpdateService/FirmwareInventory",
}
LCLOG_RESPONSE = {
    "@odata.context": "/redfish/v1/$metadata#LogEntryCollection.LogEntryCollection",
    "@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries",
    "@odata.type": "#LogEntryCollection.LogEntryCollection",
    "Description": "LC Logs for this manager",
    "Members": [
        {
            "@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries/1735",
            "@odata.type": "#LogEntry.v1_6_1.LogEntry",
            "Created": "2022-06-22T17:01:17-05:00",
            "Description": "Log Entry 1735",
            "EntryType": "Oem",
            "Id": "1735",
            "Links": {"OriginOfCondition": {"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1"}},
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
            "@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries/1734",
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
            "@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries/1692",
            "@odata.type": "#LogEntry.v1_6_1.LogEntry",
            "Created": "2022-06-22T16:42:55-05:00",
            "Description": "Log Entry 1692",
            "EntryType": "Oem",
            "Id": "1692",
            "Links": {},
            "Message": "The iDRAC firmware was rebooted with the " "following reason: user initiated.",
            "MessageArgs": ["user initiated"],
            "MessageArgs@odata.count": 1,
            "MessageId": "RAC0182",
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
    "Members@odata.nextLink": "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Lclog/Entries?$skip=50",
    "Name": "Log Entry Collection",
}

LCLOG_RESPONSE_NO_MESSAGE = deepcopy(LCLOG_RESPONSE)
LCLOG_RESPONSE_NO_MESSAGE["Members"] = []


def add_accounts_mock_responses(requests_mock):
    """Setup requests mock URLs and return payloads for all the existing users."""
    requests_mock.get("/redfish/v1/Managers/iDRAC.Embedded.1/Accounts", json=ACCOUNTS_RESPONSE)
    users = {"1": "user", "2": "root", "3": "guest"}
    for user_id, username in users.items():
        response = deepcopy(ACCOUNT_RESPONSE)
        response["Id"] = response["Id"].format(user_id=user_id)
        response["@odata.id"] = response["@odata.id"].format(user_id=user_id)
        response["UserName"] = username
        requests_mock.get(
            f"/redfish/v1/AccountService/Accounts/{user_id}", json=response, headers={"ETag": f"12345-{user_id}"}
        )


class TestRedfish:
    """Tests for the Redfish class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.redfish = redfish.Redfish("test.example.org", "root", "mysecret", dry_run=False)
        self.redfish_dry_run = redfish.Redfish("test.example.org", "root", "mysecret", dry_run=True)
        self.requests_mock = requests_mock

    def test_property_magic_str(self):
        """It should equal the fqdn."""
        assert str(self.redfish) == "root@test.example.org"

    def test_property_fqdn(self):
        """It should equal the fqdn."""
        assert self.redfish.fqdn == "test.example.org"

    @pytest.mark.parametrize("response, generation", ((MODEL_RESPONSE, 14), (MODEL_RESPONSE_BAD, 1)))
    def test_property_generation(self, response, generation):
        """It should return the generation."""
        self.requests_mock.get("/redfish/v1/Managers/iDRAC.Embedded.1?$select=Model", json=response)
        assert self.redfish.generation == generation
        # assert twice to check cached version
        assert self.redfish.generation == generation

    def test_property_pushuri(self):
        """It should return the pushuri."""
        self.requests_mock.get("/redfish/v1/UpdateService?$select=HttpPushUri", json=PUSHURI_RESPONSE)
        assert self.redfish.pushuri == "/redfish/v1/UpdateService/FirmwareInventory"
        # assert twice to check cached version
        assert self.redfish.pushuri == "/redfish/v1/UpdateService/FirmwareInventory"

    def test_most_recent_member(self):
        """It should return the item with the most recent date."""
        data = [
            {"date": "2022-01-01T00:00:00-00:00"},
            {"date": "1970-01-01T00:00:00-00:00"},
            {"date": "1971-01-01T00:00:00-00:00"},
        ]
        assert self.redfish.most_recent_member(data, "date") == {"date": "2022-01-01T00:00:00-00:00"}

    @pytest.mark.parametrize(
        "response, reboot_time",
        ((LCLOG_RESPONSE, "2022-06-22T16:42:55-05:00"), (LCLOG_RESPONSE_NO_MESSAGE, "1970-01-01T00:00:00-00:00")),
    )
    def test_last_reboot(self, response, reboot_time):
        """Return the last reboot time."""
        reboot_time = datetime.fromisoformat(reboot_time)
        self.requests_mock.get("/redfish/v1/Managers/iDRAC.Embedded.1/Logs/Lclog", json=response)
        assert self.redfish.last_reboot() == reboot_time

    @pytest.mark.parametrize("generation", (1, 13, 14))
    @mock.patch("spicerack.redfish.time.sleep")
    @mock.patch("spicerack.redfish.Redfish.last_reboot")
    @mock.patch("spicerack.redfish.Redfish.check_connection")
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
    @mock.patch("spicerack.redfish.Redfish.last_reboot")
    @mock.patch("spicerack.redfish.Redfish.check_connection")
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
        assert "Failed to perform GET request to https://test.example.org/redfish" in caplog.text

    def test_request_ok(self):
        """It should perform the provided request and return it."""
        self.requests_mock.get("/redfish", json={"v1": "/redfish/v1/"})
        response = self.redfish.request("get", "/redfish")
        assert response.json() == {"v1": "/redfish/v1/"}
        assert response.status_code == 200

    def test_request_response_wrong_status_code(self):
        """It should raise a RedfishError if the request returns an error status code."""
        self.requests_mock.post("/redfish", json={"error": {"code": "1.0", "message": "error"}}, status_code=405)
        with pytest.raises(
            redfish.RedfishError, match="POST https://test.example.org/redfish returned HTTP 405 with message"
        ):
            self.redfish.request("post", "/redfish", json={"key": "value"})

    def test_request_response_raises(self):
        """It should raise a RedfishError if the request failes to be performed."""
        self.requests_mock.get("/redfish", exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(
            redfish.RedfishError, match="Failed to perform GET request to https://test.example.org/redfish"
        ):
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

    def test_connection_fail(self):
        """It should raise a RedfishError if unable to connect to the Redfish API."""
        self.requests_mock.get("/redfish", status_code=400)
        with pytest.raises(redfish.RedfishError, match="GET https://test.example.org/redfish returned HTTP 400"):
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
        self.redfish = redfish.RedfishDell("test.example.org", "root", "mysecret", dry_run=False)
        self.requests_mock = requests_mock

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
