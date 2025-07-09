"""Cookbook module tests."""

from unittest import mock

import pytest

from spicerack import Spicerack, cookbook


class Cookbook(cookbook.CookbookBase):
    """Cookbook class used in the tests."""

    def get_runner(self, _):
        """As required by Spicerack APIs."""
        return CookbookRunner()


class CookbookRunner(cookbook.CookbookRunnerBase):
    """Cookbook runner class used in the tests."""

    def run(self):
        """As required by Spicerack APIs."""


class TestCookbookBase:
    """Test class for the CookbookBase class."""

    def setup_method(self):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.cookbook = Cookbook(mock.MagicMock(spec_set=Spicerack))

    def test_argument_parser_empty_ok(self):
        """If using the parent class argument parser without options it should return an empty argument parser."""
        parser = self.cookbook.argument_parser()
        parsed_args = parser.parse_args([])
        assert not hasattr(parsed_args, "reason")
        assert not hasattr(parsed_args, "task_id")

    @pytest.mark.parametrize("argument_task_required", (False, True))
    @pytest.mark.parametrize("arg_name", ("-t", "--task-id"))
    def test_argument_parser_task(self, arg_name, argument_task_required):
        """If the task ID argument is requested, either optionally or mandatory, it should be added."""
        self.cookbook.argument_task_required = argument_task_required
        parser = self.cookbook.argument_parser()
        args = [arg_name, "T12345"]
        parsed_args = parser.parse_args(args)
        assert parsed_args.task_id == "T12345"
        assert not hasattr(parsed_args, "reason")

    @pytest.mark.parametrize("argument_reason_required", (False, True))
    @pytest.mark.parametrize("arg_name", ("-r", "--reason"))
    def test_argument_parser_reason(self, arg_name, argument_reason_required):
        """If the reason argument is requested, either optionally or mandatory, it should be added."""
        self.cookbook.argument_reason_required = argument_reason_required
        parser = self.cookbook.argument_parser()
        args = [arg_name, "Some reason"]
        parsed_args = parser.parse_args(args)
        assert parsed_args.reason == "Some reason"
        assert not hasattr(parsed_args, "task_id")

    @pytest.mark.parametrize("argument_task_required", (False, True))
    @pytest.mark.parametrize("task_name", ("-t", "--task-id"))
    @pytest.mark.parametrize("argument_reason_required", (False, True))
    @pytest.mark.parametrize("reason_name", ("-r", "--reason"))
    def test_argument_parser_reason_task(
        self, reason_name, argument_reason_required, task_name, argument_task_required
    ):
        """If both the task ID and the reason argument are requested, they should be added."""
        self.cookbook.argument_task_required = argument_task_required
        self.cookbook.argument_reason_required = argument_reason_required
        parser = self.cookbook.argument_parser()
        args = [reason_name, "Some reason", task_name, "T12345"]
        parsed_args = parser.parse_args(args)
        assert parsed_args.reason == "Some reason"
        assert parsed_args.task_id == "T12345"

    def test_argument_parser_reason_task_optional(self):
        """If the task ID and the reason argument are requested as optional, it shouldn't error if they are not set."""
        self.cookbook.argument_task_required = False
        self.cookbook.argument_reason_required = False
        parser = self.cookbook.argument_parser()
        parsed_args = parser.parse_args([])
        assert parsed_args.reason is None
        assert parsed_args.task_id == ""

    @pytest.mark.parametrize(
        "kwargs",
        (
            {"argument_task_required": True},
            {"argument_reason_required": True},
            {"argument_task_required": True, "argument_reason_required": True},
        ),
    )
    def test_argument_parser_missing_mandatory_argument(self, kwargs):
        """If the task ID or the reason argument are requested as mandatory, if the args are not set should raise."""
        for key, value in kwargs.items():
            setattr(self.cookbook, key, value)
        parser = self.cookbook.argument_parser()
        with pytest.raises(SystemExit, match="2"):
            parser.parse_args([])

    @pytest.mark.parametrize(
        "task",
        (
            "T",
            "123",
            "T123456789",
            "A",
            "A123",
        ),
    )
    @pytest.mark.parametrize("arg_name", ("-t", "--task-id"))
    def test_argument_parser_task_invalid(self, arg_name, task):
        """If the provided task ID doesn't match a Phabricator task ID format it should raise."""
        self.cookbook.argument_task_required = False
        parser = self.cookbook.argument_parser()
        with pytest.raises(SystemExit, match="2"):
            parser.parse_args([arg_name, task])

    @pytest.mark.parametrize(
        "reason",
        (
            "",
            'reason "with quotes"',
            '"',
        ),
    )
    @pytest.mark.parametrize("arg_name", ("-r", "--reason"))
    def test_argument_parser_reason_invalid(self, arg_name, reason):
        """If the provided reason is not valid it should raise."""
        self.cookbook.argument_reason_required = False
        parser = self.cookbook.argument_parser()
        with pytest.raises(SystemExit, match="2"):
            parser.parse_args([arg_name, reason])
