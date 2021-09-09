"""Administrative module tests."""
import pytest

from spicerack import administrative


def test_reason_init():
    """It should initalize a Reason instance with the mandatory parameters."""
    reason = administrative.Reason("Reason message", "user1", "host1")
    assert str(reason) == "Reason message - user1@host1"


def test_reason_init_with_task():
    """It should initalize a Reason instance with the optional task ID."""
    reason = administrative.Reason("Reason message", "user1", "host1", task_id="T12345")
    assert str(reason) == "Reason message - user1@host1 - T12345"


@pytest.mark.parametrize(
    "failing_param_name, args, kwargs",
    (
        ("_reason", ['Reason with "double quotes"', "user1", "host1"], {"task_id": ""}),
        ("_username", ["Reason message", 'user"', "host1"], {"task_id": ""}),
        ("_hostname", ["Reason message", "user1", 'host1"'], {"task_id": ""}),
        ("_task_id", ["Reason message", "user1", "host1"], {"task_id": 'T"'}),
    ),
)
def test_reason_init_double_quotes_in_params(failing_param_name, args, kwargs):
    """It should raise ReasonError if any of the parameters contains double quotes."""
    with pytest.raises(
        administrative.ReasonError,
        match=f"Property {failing_param_name} cannot contain double quotes",
    ):
        administrative.Reason(*args, **kwargs)


def test_reason_reason():
    """It should return the reason."""
    reason = administrative.Reason("Reason message", "user1", "host1")
    assert reason.reason == "Reason message"


def test_reason_owner():
    """It should return the owner part."""
    reason = administrative.Reason("Reason message", "user1", "host1")
    assert reason.owner == "user1@host1"


def test_reason_hostname():
    """It should return the hostname."""
    reason = administrative.Reason("Reason message", "user1", "host1")
    assert reason.hostname == "host1"


def test_reason_quoted():
    """It should return the double quoted string representation of the instance."""
    reason = administrative.Reason("Reason message", "user1", "host1")
    assert reason.quoted() == '"Reason message - user1@host1"'


def test_reason_task_id_without_task():
    """It should return None for the missing task ID."""
    reason = administrative.Reason("Reason message", "user1", "host1")
    assert reason.task_id is None


def test_reason_task_id_with_task():
    """It should return the task ID."""
    reason = administrative.Reason("Reason message", "user1", "host1", task_id="T12345")
    assert reason.task_id == "T12345"
