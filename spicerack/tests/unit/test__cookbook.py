"""Cookbook module tests."""
import logging
import shutil
from pathlib import Path
from unittest import mock

import pytest

from spicerack import Spicerack, _cookbook, _menu, cookbook
from spicerack.tests import SPICERACK_TEST_PARAMS, get_fixture_path
from spicerack.tests.unit.test__log import _reset_logging_module

COOKBOOKS_BASE_PATH = Path("spicerack/tests/fixtures/cookbook")
LIST_COOKBOOKS_ALL = """cookbooks
|-- class_api
|   |-- class_api.call_another_cookbook
|   |-- class_api.example
|   |-- class_api.get_runner_raise
|   |-- class_api.multiple.CookbookA
|   |-- class_api.multiple.CookbookB
|   |-- class_api.rollback
|   |-- class_api.rollback_raise
|   |-- class_api.runtime_description
|   `-- class_api.runtime_description_raise
|-- cookbook
|-- group1
|   `-- group1.cookbook1
|-- group2
|   |-- group2.cookbook2
|   |-- group2.subgroup1
|   |   `-- group2.subgroup1.cookbook3
|   `-- group2.zcookbook4
|-- group3
|   |-- group3.argparse_ok
|   |-- group3.argument_parser_raise_system_exit
|   |-- group3.get_argument_parser_raise
|   |-- group3.get_argument_parser_raise_system_exit_str
|   |-- group3.keyboard_interrupt
|   |-- group3.non_zero_exit
|   |-- group3.raise_exception
|   |-- group3.raise_system_exit_0
|   |-- group3.raise_system_exit_9
|   |-- group3.raise_system_exit_str
|   `-- group3.subgroup3
|       `-- group3.subgroup3.cookbook4
|-- multiple.CookbookA
|-- multiple.CookbookB
`-- root
"""
LIST_COOKBOOKS_ALL_VERBOSE = """cookbooks
|-- class_api: Class API Test Cookbooks.
|   |-- class_api.call_another_cookbook: A cookbook that calls another cookbook.
|   |-- class_api.example: -
|   |-- class_api.get_runner_raise: Class API get_runner raise cookbook.
|   |-- class_api.multiple.CookbookA: Multiple cookbook classes.
|   |-- class_api.multiple.CookbookB: Multiple cookbook classes.
|   |-- class_api.rollback: Class API rollback cookbook.
|   |-- class_api.rollback_raise: Class API rollback_raise cookbook.
|   |-- class_api.runtime_description: Class API cookbook that overrides runtime_description.
|   `-- class_api.runtime_description_raise: Class API runtime_description raise cookbook.
|-- cookbook: Top level class cookbook.
|-- group1: Group1 Test Cookbooks.
|   `-- group1.cookbook1: Group1 Cookbook1.
|-- group2: -
|   |-- group2.cookbook2: Group2 Cookbook2.
|   |-- group2.subgroup1: -
|   |   `-- group2.subgroup1.cookbook3: Group2 Subgroup1 Cookbook3.
|   `-- group2.zcookbook4: UNKNOWN (unable to detect title)
|-- group3: -
|   |-- group3.argparse_ok: Group3 argparse_ok.
|   |-- group3.argument_parser_raise_system_exit: Group3 argument_parser() raise SystemExit.
|   |-- group3.get_argument_parser_raise: Group3 get argument_parser() raise.
|   |-- group3.get_argument_parser_raise_system_exit_str: Group3 get argument_parser() raise SystemExit with a string.
|   |-- group3.keyboard_interrupt: Group3 Raise KeyboardInterrupt.
|   |-- group3.non_zero_exit: Group3 Non-Zero return code.
|   |-- group3.raise_exception: Group3 Raise Exception.
|   |-- group3.raise_system_exit_0: Group3 Raise SystemExit(0).
|   |-- group3.raise_system_exit_9: Group3 Raise SystemExit(9).
|   |-- group3.raise_system_exit_str: Group3 Raise SystemExit('message').
|   `-- group3.subgroup3: -
|       `-- group3.subgroup3.cookbook4: Group3 Subgroup3 Cookbook4.
|-- multiple.CookbookA: Multiple cookbook classes.
|-- multiple.CookbookB: Multiple cookbook classes.
`-- root: Top level cookbook.
"""
LIST_COOKBOOKS_GROUP3 = """cookbooks
`-- group3
    |-- group3.argparse_ok
    |-- group3.argument_parser_raise_system_exit
    |-- group3.get_argument_parser_raise
    |-- group3.get_argument_parser_raise_system_exit_str
    |-- group3.keyboard_interrupt
    |-- group3.non_zero_exit
    |-- group3.raise_exception
    |-- group3.raise_system_exit_0
    |-- group3.raise_system_exit_9
    |-- group3.raise_system_exit_str
    `-- group3.subgroup3
        `-- group3.subgroup3.cookbook4
"""
LIST_COOKBOOKS_GROUP3_SUBGROUP3 = """cookbooks
`-- group3
    `-- group3.subgroup3
        `-- group3.subgroup3.cookbook4
"""
COOKBOOKS_MENU_TTY = """#--- cookbooks args=[] ---#
[0/9] class_api: Class API Test Cookbooks.
[NOTRUN] cookbook: Top level class cookbook.
[0/1] group1: Group1 Test Cookbooks.
[0/3] group2: -
[0/11] group3: -
[NOTRUN] multiple.CookbookA: Multiple cookbook classes.
[NOTRUN] multiple.CookbookB: Multiple cookbook classes.
[NOTRUN] root: Top level cookbook.
q - Quit
h - Help
"""
COOKBOOKS_MENU_NOTTY = """#--- cookbooks args=[] ---#
[0/9] class_api: Class API Test Cookbooks.
[NOTRUN] cookbook: Top level class cookbook.
[0/1] group1: Group1 Test Cookbooks.
[0/3] group2: -
[0/11] group3: -
[NOTRUN] multiple.CookbookA: Multiple cookbook classes.
[NOTRUN] multiple.CookbookB: Multiple cookbook classes.
[NOTRUN] root: Top level cookbook.
q - Quit
h - Help
Not a tty, exiting.
"""
COOKBOOKS_GROUP1_MENU = """#--- Group1 Test Cookbooks. args=[] ---#
[NOTRUN] cookbook1: Group1 Cookbook1.
b - Back to parent menu
h - Help
"""
COOKBOOKS_GROUP2_MENU = """#--- group2 args=[] ---#
[NOTRUN] cookbook2: Group2 Cookbook2.
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
h - Help
"""
COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN = """[{'argument': None, 'k': False}, False, False]
#--- group2 args=[] ---#
[PASS] cookbook2: Group2 Cookbook2.
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
h - Help
"""
COOKBOOKS_GROUP2_SUBGROUP1_MENU = """#--- subgroup1 args=[] ---#
[NOTRUN] cookbook3: Group2 Subgroup1 Cookbook3.
b - Back to parent menu
h - Help
"""


def test_argument_parser_converts_path():
    """It should convert a path-based cookbook into a module path."""
    argv = ["group1/cookbook1.py"]
    args = _cookbook.argument_parser().parse_args(argv)
    assert args.cookbook == "group1.cookbook1"


def test_argument_parser_keeps_module():
    """It should keep a module-based cookbook as it is."""
    argv = ["group1.cookbook1"]
    args = _cookbook.argument_parser().parse_args(argv)
    assert args.cookbook == argv[0]


def test_argument_parser_accept_empty():
    """With no args it should not fail."""
    args = _cookbook.argument_parser().parse_args([])
    assert args.cookbook == ""


def test_parse_args_list():
    """Passing -l/--list should keep the cookbook None and set list."""
    argv = ["--list"]
    args = _cookbook.argument_parser().parse_args(argv)
    assert args.list
    assert args.cookbook == ""


def test_main_wrong_instance_config(capsys):
    """If the configuration file has invalid instance_params it should print an error and exit."""
    ret = _cookbook.main(["-c", str(get_fixture_path("config_wrong_overrides.yaml")), "cookbook"])
    _, err = capsys.readouterr()
    assert ret == 1
    assert "Unable to instantiate Spicerack, check your configuration" in err
    _reset_logging_module()


def test_main_call_another_cookbook_ok(capsys):
    """It should execute the cookbook that calls another cookbook."""
    ret = _cookbook.main(
        ["-c", str(get_fixture_path("config.yaml")), "class_api.call_another_cookbook", "class_api.example"]
    )
    _, err = capsys.readouterr()
    assert ret == 0
    expected = [
        "START - Cookbook class_api.call_another_cookbook",
        "START - Cookbook class_api.example",
        "END (PASS) - Cookbook class_api.example (exit_code=0)",
        "END (PASS) - Cookbook class_api.call_another_cookbook (exit_code=0)",
    ]
    for line in expected:
        assert line in err
    _reset_logging_module()


def test_main_call_another_cookbook_not_found(capsys):
    """It should fail to call another cookbook if it doesn't exists."""
    ret = _cookbook.main(
        ["-c", str(get_fixture_path("config.yaml")), "class_api.call_another_cookbook", "class_api.not_existent"]
    )
    _, err = capsys.readouterr()
    assert ret == cookbook.EXCEPTION_RETCODE
    assert "SpicerackError: Unable to find cookbook class_api.not_existent" in err
    assert "END (FAIL) - Cookbook class_api.call_another_cookbook (exit_code=99)" in err
    _reset_logging_module()


class TestCookbookCollection:
    """Test class for the CookbookCollection class."""

    def setup_method(self):
        """Initialize the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.spicerack = Spicerack(verbose=False, dry_run=False, **SPICERACK_TEST_PARAMS)
        self.spicerack_dry_run = Spicerack(verbose=False, dry_run=True, **SPICERACK_TEST_PARAMS)
        self.spicerack_verbose = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    def teardown_method(self):
        """Tear down the test setting resetting the logging module."""
        _reset_logging_module()

    @pytest.mark.parametrize(
        "path_filter, verbose, expected",
        (
            ("", False, LIST_COOKBOOKS_ALL),
            ("", True, LIST_COOKBOOKS_ALL_VERBOSE),
            ("group3", False, LIST_COOKBOOKS_GROUP3),
            ("group3.subgroup3", False, LIST_COOKBOOKS_GROUP3_SUBGROUP3),
            ("group3.non_existent", False, ""),
        ),
    )
    def test_cookbooks_str(self, monkeypatch, path_filter, verbose, expected):
        """The string representation of the CookbookCollection should print all the cookbooks as a tree."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        if not path_filter and not verbose:  # For the first test ensure there is no __pycache__ directory.
            shutil.rmtree(COOKBOOKS_BASE_PATH / "cookbooks" / "__pycache__", ignore_errors=True)

        spicerack = self.spicerack
        if verbose:
            spicerack = self.spicerack_verbose
        cookbooks = _cookbook.CookbookCollection(COOKBOOKS_BASE_PATH, [], spicerack, path_filter=path_filter)
        assert cookbooks.menu.get_tree() == expected

    def test_cookbooks_non_existent(self):
        """The CookbookCollection class initialized with an empty path should not collect any cookbook."""
        cookbooks = _cookbook.CookbookCollection(COOKBOOKS_BASE_PATH / "non_existent", [], self.spicerack)
        assert cookbooks.menu.get_tree() == ""

    @pytest.mark.parametrize(
        "module, err_messages, absent_err_messages, code, args",
        (
            (
                "cookbook",
                [
                    "START - Cookbook cookbook",
                    "END (PASS) - Cookbook cookbook (exit_code=0)",
                ],
                [],
                0,
                [],
            ),
            ("cookbook", [], ["START - Cookbook", "END ("], 2, ["arg1"]),
            (
                "group3.non_zero_exit",
                ["END (FAIL) - Cookbook group3.non_zero_exit (exit_code=1)"],
                [],
                1,
                [],
            ),
            (
                "group3.non_zero_exit",
                ["END (FAIL) - Cookbook group3.non_zero_exit (exit_code=1)"],
                [],
                1,
                [],
            ),
            (
                "group3.non_existent",
                ["Unable to find cookbook"],
                [],
                cookbook.NOT_FOUND_RETCODE,
                [],
            ),
            ("group3.argparse_ok", [], ["START - Cookbook", "END ("], 0, ["-h"]),
            (
                "group3.invalid_syntax",
                ["invalid syntax (invalid_syntax.py, line 7)"],
                [],
                cookbook.NOT_FOUND_RETCODE,
                [],
            ),
            (
                "group3.keyboard_interrupt",
                ["Ctrl+c pressed"],
                [],
                cookbook.INTERRUPTED_RETCODE,
                [],
            ),
            (
                "group3.get_argument_parser_raise",
                ["raised while getting argument parser for cookbook"],
                ["START - Cookbook", "END ("],
                cookbook.GET_ARGS_PARSER_FAIL_RETCODE,
                [],
            ),
            (
                "group3.get_argument_parser_raise_system_exit_str",
                ["SystemExit('argument_parser')"],
                ["START - Cookbook", "END ("],
                cookbook.GET_ARGS_PARSER_FAIL_RETCODE,
                [],
            ),
            (
                "group3.argument_parser_raise_system_exit",
                [],
                ["group3.argument_parser_raise_system_exit", "START - Cookbook", "END ("],
                2,
                [],
            ),
            (
                "group3.raise_exception",
                ["Exception: Something went wrong"],
                [],
                cookbook.EXCEPTION_RETCODE,
                [],
            ),
            ("group3.raise_system_exit_0", ["SystemExit(0) raised"], [], 0, []),
            ("group3.raise_system_exit_9", ["SystemExit(9) raised"], [], 9, []),
            (
                "group3.raise_system_exit_str",
                ["SystemExit('message') raised"],
                [],
                cookbook.EXCEPTION_RETCODE,
                [],
            ),
            (
                "class_api.example",
                [
                    "START - Cookbook class_api.example",
                    "END (PASS) - Cookbook class_api.example (exit_code=0)",
                ],
                [],
                0,
                [],
            ),
            (
                "class_api.multiple.CookbookA",
                [
                    "START - Cookbook class_api.multiple.CookbookA",
                    "END (PASS) - Cookbook class_api.multiple.CookbookA (exit_code=0)",
                ],
                [],
                0,
                [],
            ),
            (
                "class_api.get_runner_raise",
                [],
                ["START - Cookbook", "END ("],
                cookbook.CLASS_FAIL_INIT_RETCODE,
                [],
            ),
            (
                "class_api.runtime_description",
                [
                    "START - Cookbook class_api.runtime_description Runtime description",
                    "END (PASS) - Cookbook class_api.runtime_description (exit_code=0) Runtime description",
                ],
                [],
                0,
                [],
            ),
            (
                "class_api.runtime_description_raise",
                [
                    "START - Cookbook class_api.runtime_description_raise",
                    "END (PASS) - Cookbook class_api.runtime_description_raise (exit_code=0)",
                ],
                [],
                0,
                [],
            ),
            (
                "class_api.rollback",
                [
                    "START - Cookbook class_api.rollback",
                    "run has raised",
                    "rollback called",
                    "END (FAIL) - Cookbook class_api.rollback (exit_code=99)",
                ],
                [],
                cookbook.EXCEPTION_RETCODE,
                [],
            ),
            (
                "class_api.rollback_raise",
                [
                    "START - Cookbook class_api.rollback_raise",
                    "rollback has raised",
                    "END (FAIL) - Cookbook class_api.rollback_raise (exit_code=93)",
                ],
                [],
                cookbook.ROLLBACK_FAIL_RETCODE,
                [],
            ),
        ),
    )
    def test_main_execute_cookbook(  # pylint: disable=too-many-arguments
        self, tmpdir, caplog, module, err_messages, absent_err_messages, code, args
    ):
        """Calling main with the given cookbook and args should execute it."""
        config = {
            "cookbooks_base_dir": COOKBOOKS_BASE_PATH,
            "logs_base_dir": tmpdir.strpath,
        }
        with mock.patch("spicerack._cookbook.load_yaml_config", lambda config_dir: config):
            with mock.patch("spicerack._cookbook.Spicerack", return_value=self.spicerack):
                with caplog.at_level(logging.INFO):
                    ret = _cookbook.main([module] + args)

        assert ret == code
        for message in err_messages:
            assert message in caplog.text
        for message in absent_err_messages:
            assert message not in caplog.text

    def test_main_execute_cookbook_invalid_args(self, tmpdir, capsys, caplog):
        """Calling a cookbook with the wrong args should let argparse print its message."""
        config = {
            "cookbooks_base_dir": COOKBOOKS_BASE_PATH,
            "logs_base_dir": tmpdir.strpath,
        }
        with mock.patch("spicerack._cookbook.load_yaml_config", lambda config_dir: config):
            with mock.patch("spicerack._cookbook.Spicerack", return_value=self.spicerack):
                with caplog.at_level(logging.INFO):
                    ret = _cookbook.main(["group3.argparse_ok", "--invalid"])

        assert ret == 2
        _, err = capsys.readouterr()
        assert "group3.argparse_ok: error: unrecognized arguments" in err
        for message in ("START - Cookbook", "END ("):
            assert message not in caplog.text

    def test_main_execute_dry_run(self, capsys, tmpdir):
        """Calling main() with a cookbook and dry_run mode should execute it and set the dry run mode."""
        config = {
            "cookbooks_base_dir": COOKBOOKS_BASE_PATH,
            "logs_base_dir": tmpdir.strpath,
        }
        with mock.patch("spicerack._cookbook.load_yaml_config", lambda config_dir: config):
            with mock.patch("spicerack._cookbook.Spicerack", return_value=self.spicerack_dry_run):
                ret = _cookbook.main(["-d", "root"])

        assert ret == 0
        _, err = capsys.readouterr()
        assert "DRY-RUN" in err

    def test_main_list(self, tmpdir, capsys, caplog):
        """Calling main() with the -l/--list option should print the available cookbooks."""
        config = {
            "cookbooks_base_dir": COOKBOOKS_BASE_PATH,
            "logs_base_dir": tmpdir.strpath,
        }
        with mock.patch("spicerack._cookbook.load_yaml_config", lambda config_dir: config):
            with mock.patch("spicerack._cookbook.Spicerack", return_value=self.spicerack):
                with caplog.at_level(logging.INFO):
                    ret = _cookbook.main(["-l"])

        out, _ = capsys.readouterr()

        assert ret == 0
        assert out == LIST_COOKBOOKS_ALL
        lines = [
            "Failed to import module cookbooks.group3.invalid_syntax: invalid syntax (invalid_syntax.py, line 7)",
            "Failed to import module cookbooks.group3.invalid_subgroup: invalid syntax (__init__.py, line 2)",
        ]
        for line in lines:
            assert line in caplog.text

    def test_cookbooks_menu_status(self, monkeypatch):
        """Calling status on a TreeItem should show the completed and total tasks."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        cookbooks = _cookbook.CookbookCollection(COOKBOOKS_BASE_PATH, [], self.spicerack)
        menu = cookbooks.get_item("")
        assert menu.status == "0/28"

    def test_cookbooks_menu_status_done(self, monkeypatch):
        """Calling status on a TreeItem with all tasks completed should return DONE."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        cookbooks = _cookbook.CookbookCollection(COOKBOOKS_BASE_PATH, [], self.spicerack, path_filter="group1")
        menu = cookbooks.get_item("group1")
        assert menu.status == "0/1"
        item = cookbooks.get_item("group1.cookbook1")
        item.run()
        assert menu.status == "DONE"

    @mock.patch("spicerack._cookbook.CookbookItem", side_effect=_menu.MenuError("fail to init"))
    def test_cookbooks_menu_cookbook_init_fail(self, mocked_cookbook_item, caplog, monkeypatch):
        """When a CookbookItem object fail to get initialized it should catch the MenuError, log it and continue."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        with caplog.at_level(logging.INFO):
            cookbooks = _cookbook.CookbookCollection(COOKBOOKS_BASE_PATH, [], self.spicerack, path_filter="cookbook")
            menu = cookbooks.get_item(".".join((cookbooks.cookbooks_module_prefix, "group1")))
        assert menu is None
        assert "fail to init" in caplog.text
        assert mocked_cookbook_item.called

    def test_cookbooks_cookbook_init_fail(self):
        """When a CookbookItem object fail to get initialized it should catch the MenuError, log it and continue."""

        class NotCookbookBaseSubclass:
            """Just a class that doesn't inherit from CookbookBase."""

        with pytest.raises(_menu.MenuError, match="is not a subclass of CookbookBase"):
            _menu.CookbookItem(NotCookbookBaseSubclass, [], self.spicerack)

    @pytest.mark.parametrize(
        "tty, answer, output",
        (
            (False, "q", COOKBOOKS_MENU_NOTTY),
            (True, "q", COOKBOOKS_MENU_TTY),
            (True, KeyboardInterrupt, COOKBOOKS_MENU_TTY + "QUIT\n"),
            (True, ["", "q"], COOKBOOKS_MENU_TTY + COOKBOOKS_MENU_TTY),
            (
                True,
                ["invalid", "q"],
                COOKBOOKS_MENU_TTY + "==> Invalid input <==\n" + COOKBOOKS_MENU_TTY,
            ),
            (
                True,
                ["group1", "b", "q"],
                COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP1_MENU + COOKBOOKS_MENU_TTY,
            ),
            (
                True,
                ["group2", "cookbook2", "b", "q"],
                COOKBOOKS_MENU_TTY
                + COOKBOOKS_GROUP2_MENU
                + COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN
                + COOKBOOKS_MENU_TTY.replace("[0/3] group2", "[1/3] group2"),
            ),
            (
                True,
                ["group2", "cookbook2 --argument value", "b", "q"],
                COOKBOOKS_MENU_TTY
                + COOKBOOKS_GROUP2_MENU
                + COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN.replace("'argument': None", "'argument': 'value'")
                + COOKBOOKS_MENU_TTY.replace("[0/3] group2", "[1/3] group2"),
            ),
            (
                True,
                ["group2 -k", "cookbook2", "b", "q"],
                COOKBOOKS_MENU_TTY
                + COOKBOOKS_GROUP2_MENU.replace("[]", "['-k']")
                + COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN.replace("[]", "['-k']").replace("'k': False", "'k': True")
                + COOKBOOKS_MENU_TTY.replace("[0/3] group2", "[1/3] group2"),
            ),
            (
                True,
                "h",
                COOKBOOKS_MENU_TTY
                + _menu.HELP_MESSAGE.format(statuses=_cookbook.CookbookItem.statuses)
                + "\n"
                + COOKBOOKS_MENU_TTY,
            ),
        ),
    )
    @mock.patch("spicerack._cookbook.sys.stdout.isatty")
    @mock.patch("builtins.input")
    def test_cookbooks_main_menu(
        self, mocked_input, mocked_tty, tty, answer, output, capsys, tmpdir
    ):  # pylint: disable=too-many-arguments
        """Calling main() with a menu should show the menu and allow to interact with it."""
        mocked_tty.return_value = tty
        mocked_input.side_effect = answer
        config = {
            "cookbooks_base_dir": COOKBOOKS_BASE_PATH,
            "logs_base_dir": tmpdir.strpath,
        }
        with mock.patch("spicerack._cookbook.load_yaml_config", lambda config_dir: config):
            with mock.patch("spicerack._cookbook.Spicerack", return_value=self.spicerack):
                ret = _cookbook.main([])

        out, _ = capsys.readouterr()
        assert ret == 0
        assert out == output

    @mock.patch("spicerack._cookbook.sys.stdout.isatty")
    @mock.patch("builtins.input")
    def test_cookbooks_submenu(self, mocked_input, mocked_tty, capsys, tmpdir):
        """Calling main() with a menu should show the menu and allow to interact with it."""
        mocked_tty.return_value = True
        mocked_input.side_effect = ["subgroup1", "b", "q"]
        config = {
            "cookbooks_base_dir": COOKBOOKS_BASE_PATH,
            "logs_base_dir": tmpdir.strpath,
        }
        with mock.patch("spicerack._cookbook.load_yaml_config", lambda config_dir: config):
            with mock.patch("spicerack._cookbook.Spicerack", return_value=self.spicerack):
                ret = _cookbook.main(["group2"])

        out, _ = capsys.readouterr()
        assert ret == 0
        group2 = COOKBOOKS_GROUP2_MENU.replace("b - Back to parent menu", "q - Quit")
        assert out == group2 + COOKBOOKS_GROUP2_SUBGROUP1_MENU + group2
