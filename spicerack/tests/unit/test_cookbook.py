"""Cookbook module tests."""
import os
import shutil

from unittest import mock

import pytest

from spicerack import cookbook, Spicerack

from spicerack.tests import caplog_not_available, SPICERACK_TEST_PARAMS


COOKBOOKS_BASE_PATH = 'spicerack/tests/fixtures/cookbook'
LIST_COOKBOOKS_ALL = """cookbooks
|-- cookbook
|-- group1
|   `-- group1.cookbook1
|-- group2
|   |-- group2.cookbook2
|   |-- group2.subgroup1
|   |   `-- group2.subgroup1.cookbook3
|   `-- group2.zcookbook4
|-- group3
|   |-- group3.argparse
|   |-- group3.argument_parser_raise
|   |-- group3.argument_parser_raise_system_exit_str
|   |-- group3.keyboard_interrupt
|   |-- group3.non_zero_exit
|   |-- group3.raise_exception
|   |-- group3.raise_system_exit_0
|   |-- group3.raise_system_exit_9
|   |-- group3.raise_system_exit_str
|   `-- group3.subgroup3
|       `-- group3.subgroup3.cookbook4
`-- root
"""
LIST_COOKBOOKS_ALL_VERBOSE = """cookbooks
|-- cookbook: Top level cookbook
|-- group1: Group1 Test Cookbooks
|   `-- group1.cookbook1: Group1 Cookbook1
|-- group2: -
|   |-- group2.cookbook2: Group2 Cookbook2
|   |-- group2.subgroup1: -
|   |   `-- group2.subgroup1.cookbook3: Group2 Subgroup1 Cookbook3
|   `-- group2.zcookbook4: UNKNOWN (unable to detect title)
|-- group3: -
|   |-- group3.argparse: Group3 argparse
|   |-- group3.argument_parser_raise: Group3 argument_parser() raise
|   |-- group3.argument_parser_raise_system_exit_str: Group3 Raise SystemExit('message') in argument_parser()
|   |-- group3.keyboard_interrupt: Group3 Raise KeyboardInterrupt
|   |-- group3.non_zero_exit: Group3 Non-Zero return code
|   |-- group3.raise_exception: Group3 Raise Exception
|   |-- group3.raise_system_exit_0: Group3 Raise SystemExit(0)
|   |-- group3.raise_system_exit_9: Group3 Raise SystemExit(9)
|   |-- group3.raise_system_exit_str: Group3 Raise SystemExit('message')
|   `-- group3.subgroup3: -
|       `-- group3.subgroup3.cookbook4: Group3 Subgroup3 Cookbook4
`-- root: Top level cookbook: []
"""
LIST_COOKBOOKS_GROUP3 = """cookbooks
`-- group3
    |-- group3.argparse
    |-- group3.argument_parser_raise
    |-- group3.argument_parser_raise_system_exit_str
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
[NOTRUN] cookbook: Top level cookbook
[0/1] group1: Group1 Test Cookbooks
[0/3] group2: -
[0/10] group3: -
[NOTRUN] root: Top level cookbook: []
q - Quit
h - Help
"""
COOKBOOKS_MENU_NOTTY = """#--- cookbooks args=[] ---#
[NOTRUN] cookbook: Top level cookbook
[0/1] group1: Group1 Test Cookbooks
[0/3] group2: -
[0/10] group3: -
[NOTRUN] root: Top level cookbook: []
q - Quit
h - Help
Not a tty, exiting.
"""
COOKBOOKS_GROUP1_MENU = """#--- Group1 Test Cookbooks args=[] ---#
[NOTRUN] cookbook1: Group1 Cookbook1
b - Back to parent menu
h - Help
"""
COOKBOOKS_GROUP2_MENU = """#--- group2 args=[] ---#
[NOTRUN] cookbook2: Group2 Cookbook2
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
h - Help
"""
COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN = """[Namespace(argument=None, k=False), False, False]
#--- group2 args=[] ---#
[PASS] cookbook2: Group2 Cookbook2
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
h - Help
"""


def test_argument_parser_converts_path():
    """It should convert a path-based cookbook into a module path."""
    argv = ['group1/cookbook1.py']
    args = cookbook.argument_parser().parse_args(argv)
    assert args.cookbook == 'group1.cookbook1'


def test_argument_parser_keeps_module():
    """It should keep a module-based cookbook as it is."""
    argv = ['group1.cookbook1']
    args = cookbook.argument_parser().parse_args(argv)
    assert args.cookbook == argv[0]


def test_argument_parser_accept_empty():
    """With no args it should not fail."""
    args = cookbook.argument_parser().parse_args([])
    assert args.cookbook is None


def test_parse_args_list():
    """Passing -l/--list should keep the cookbook None and set list."""
    argv = ['--list']
    args = cookbook.argument_parser().parse_args(argv)
    assert args.list
    assert args.cookbook is None


class TestCookbooks:
    """Test class for the Cookbooks class."""

    def setup_method(self):
        """Initialize the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.spicerack = Spicerack(verbose=False, dry_run=False, **SPICERACK_TEST_PARAMS)
        self.spicerack_dry_run = Spicerack(verbose=False, dry_run=True, **SPICERACK_TEST_PARAMS)
        self.spicerack_verbose = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    @pytest.mark.parametrize('path_filter, verbose, expected', (
        (None, False, LIST_COOKBOOKS_ALL),
        (None, True, LIST_COOKBOOKS_ALL_VERBOSE),
        ('group3', False, LIST_COOKBOOKS_GROUP3),
        ('group3.subgroup3', False, LIST_COOKBOOKS_GROUP3_SUBGROUP3),
        ('group3.non_existent', False, ''),
    ))
    def test_cookbooks_str(self, monkeypatch, path_filter, verbose, expected):
        """The string representation of the Cookbooks should print all the cookbooks as a tree, based on the options."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        if path_filter is None and not verbose:  # For the first test ensure there is no __pycache__ directory.
            shutil.rmtree(os.path.join(COOKBOOKS_BASE_PATH, 'cookbooks', '__pycache__'), ignore_errors=True)

        spicerack = self.spicerack
        if verbose:
            spicerack = self.spicerack_verbose
        cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [], spicerack, path_filter=path_filter)
        assert cookbooks.menu.get_tree() == expected

    def test_cookbooks_non_existent(self):
        """The Cookbooks class initialized with an empty path should not collect any cookbook."""
        cookbooks = cookbook.Cookbooks(os.path.join(COOKBOOKS_BASE_PATH, 'non_existent'), [], self.spicerack)
        assert cookbooks.menu.get_tree() == ''

    @pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
    @pytest.mark.parametrize('module, err_messages, absent_err_messages, code, args', (
        ('cookbook', ['START - Cookbook cookbook', 'END (PASS) - Cookbook cookbook (exit_code=0)'], [], 0, []),
        ('cookbook', [], ['START - Cookbook', 'END ('], cookbook.COOKBOOK_NO_PARSER_WITH_ARGS_RETCODE, ['arg1']),
        ('group3.non_zero_exit', ['END (FAIL) - Cookbook group3.non_zero_exit (exit_code=1)'], [], 1, []),
        ('group3.non_zero_exit', ['END (FAIL) - Cookbook group3.non_zero_exit (exit_code=1)'], [], 1, []),
        ('group3.non_existent', ['Unable to find cookbook'], [], cookbook.COOKBOOK_NOT_FOUND_RETCODE, []),
        ('group3.argparse', [], ['START - Cookbook', 'END ('], 0, ['-h']),
        ('group3.invalid_syntax', ['invalid syntax (invalid_syntax.py, line 7)'], [],
         cookbook.COOKBOOK_NOT_FOUND_RETCODE, []),
        ('group3.keyboard_interrupt', ['Ctrl+c pressed'], [], cookbook.COOKBOOK_INTERRUPTED_RETCODE, []),
        ('group3.argument_parser_raise', ['raised while parsing arguments for cookbook'], ['START - Cookbook', 'END ('],
         cookbook.COOKBOOK_PARSE_ARGS_FAIL_RETCODE, []),
        ('group3.argument_parser_raise_system_exit_str', ["SystemExit('argument_parser')"],
         ['START - Cookbook', 'END ('], cookbook.COOKBOOK_PARSE_ARGS_FAIL_RETCODE, []),
        ('group3.raise_exception', ['Exception: Something went wrong'], [], cookbook.COOKBOOK_EXCEPTION_RETCODE, []),
        ('group3.raise_system_exit_0', ['SystemExit(0) raised'], [], 0, []),
        ('group3.raise_system_exit_9', ['SystemExit(9) raised'], [], 9, []),
        ('group3.raise_system_exit_str', ["SystemExit('message') raised"], [], cookbook.COOKBOOK_EXCEPTION_RETCODE, []),
    ))  # pylint: disable=too-many-arguments
    def test_main_execute_cookbook(self, tmpdir, caplog, module, err_messages, absent_err_messages, code, args):
        """Calling execute_cookbook() should intercept any exception raised."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main([module] + args)

        assert ret == code
        for message in err_messages:
            assert message in caplog.text
        for message in absent_err_messages:
            assert message not in caplog.text

    @pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
    def test_main_execute_cookbook_invalid_args(self, tmpdir, capsys, caplog):
        """Calling a cookbook with the wrong args should let argparse print its message."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['group3.argparse', '--invalid'])

        assert ret == 2
        _, err = capsys.readouterr()
        assert 'Argparse: error: unrecognized arguments' in err
        for message in ('START - Cookbook', 'END ('):
            assert message not in caplog.text

    def test_main_execute_dry_run(self, capsys, tmpdir):
        """Calling main() with a cookbook and dry_run mode should execute it and set the dry run mode."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack_dry_run):
                ret = cookbook.main(['-d', 'root'])

        assert ret == 0
        _, err = capsys.readouterr()
        assert 'DRY-RUN' in err

    @pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
    def test_main_list(self, tmpdir, capsys, caplog):
        """Calling main() with the -l/--list option should print the available cookbooks."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['-l'])

        out, _ = capsys.readouterr()

        assert ret == 0
        assert out == LIST_COOKBOOKS_ALL
        lines = ['Failed to import module cookbooks.group3.invalid_syntax: invalid syntax (invalid_syntax.py, line 7)',
                 'Failed to import module cookbooks.group3.invalid_subgroup: invalid syntax (__init__.py, line 2)']
        for line in lines:
            assert line in caplog.text

    def test_cookbooks_menu_status(self, monkeypatch):
        """Calling status on a CookbooksMenu should show the completed and total tasks."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [], self.spicerack)
        menu = cookbooks.get_item(cookbooks.cookbooks_module_prefix)
        assert menu.status == '0/16'

    def test_cookbooks_menu_status_done(self, monkeypatch):
        """Calling status on a CookbooksMenu with all tasks completed should return DONE."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [], self.spicerack, path_filter='group1')
        menu = cookbooks.get_item('.'.join((cookbooks.cookbooks_module_prefix, 'group1')))
        assert menu.status == '0/1'
        item = cookbooks.get_item('.'.join((cookbooks.cookbooks_module_prefix, 'group1', 'cookbook1')))
        item.status = item.success
        assert menu.status == 'DONE'

    @pytest.mark.parametrize('tty, answer, output', (
        (False, 'q', COOKBOOKS_MENU_NOTTY),
        (True, 'q', COOKBOOKS_MENU_TTY),
        (True, KeyboardInterrupt, COOKBOOKS_MENU_TTY + 'QUIT\n'),
        (True, ['', 'q'], COOKBOOKS_MENU_TTY + COOKBOOKS_MENU_TTY),
        (True, ['invalid', 'q'], COOKBOOKS_MENU_TTY + '==> Invalid input <==\n' + COOKBOOKS_MENU_TTY),
        (True, ['group1', 'b', 'q'], COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP1_MENU + COOKBOOKS_MENU_TTY),
        (True, ['group2', 'cookbook2', 'b', 'q'],
         COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP2_MENU + COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN + COOKBOOKS_MENU_TTY.replace(
            '[0/3] group2', '[1/3] group2')),
        (True, ['group2', 'cookbook2 --argument value', 'b', 'q'],
         COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP2_MENU +
         COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN.replace('argument=None', "argument='value'") +
         COOKBOOKS_MENU_TTY.replace('[0/3] group2', '[1/3] group2')),
        (True, ['group2 -k', 'cookbook2', 'b', 'q'],
         COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP2_MENU.replace('[]', "['-k']") +
         COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN.replace('[]', "['-k']").replace('k=False', 'k=True') +
         COOKBOOKS_MENU_TTY.replace('[0/3] group2', '[1/3] group2')),
        (True, 'h', COOKBOOKS_MENU_TTY +
         cookbook.COOKBOOKS_MENU_HELP_MESSAGE.format(statuses=cookbook.Cookbook.statuses) + '\n' + COOKBOOKS_MENU_TTY),
    ))
    @mock.patch('spicerack.cookbook.sys.stdout.isatty')
    @mock.patch('builtins.input')    # pylint: disable=too-many-arguments
    def test_cookbooks_main_menu(self, mocked_input, mocked_tty, tty, answer, output, capsys, tmpdir):
        """Calling main() with a menu should show the menu and allow to interact with it."""
        mocked_tty.return_value = tty
        mocked_input.side_effect = answer
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main([])

        out, _ = capsys.readouterr()
        assert ret == 0
        assert out == output
