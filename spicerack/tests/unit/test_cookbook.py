"""Cookbook module tests."""
import os
import shutil

from unittest import mock

import pytest

from spicerack import cookbook, Spicerack

from spicerack.tests import SPICERACK_TEST_PARAMS


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
[0/7] group3: -
[NOTRUN] root: Top level cookbook: []
q - Quit
h - Help
"""
COOKBOOKS_MENU_NOTTY = """#--- cookbooks args=[] ---#
[NOTRUN] cookbook: Top level cookbook
[0/1] group1: Group1 Test Cookbooks
[0/3] group2: -
[0/7] group3: -
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
COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN = """args=[], verbose=False, dry_run=False
#--- group2 args=[] ---#
[PASS] cookbook2: Group2 Cookbook2
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
h - Help
"""


def test_parse_args_converts_path():
    """Calling parse_args() with a path-based cookbook should convert it into a module path."""
    argv = ['group1/cookbook1.py']
    args = cookbook.parse_args(argv)
    assert args.cookbook == 'group1.cookbook1'


def test_parse_args_keeps_module():
    """Calling parse_args() with a module-based cookbook should keep it as is."""
    argv = ['group1.cookbook1']
    args = cookbook.parse_args(argv)
    assert args.cookbook == argv[0]


def test_parse_args_accept_empty():
    """Calling parse_args() without arguments should not raise error."""
    args = cookbook.parse_args([])
    assert args.cookbook is None


def test_parse_args_list():
    """Calling parse_args() with -l/--list should keep the cookbook None and set list."""
    argv = ['--list']
    args = cookbook.parse_args(argv)
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

    def test_main_execute_cookbook_ok(self, tmpdir, capsys):
        """Calling main() with a cookbook should run the cookbook."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['cookbook'])

        _, err = capsys.readouterr()
        assert ret == 0
        assert 'START - Cookbook cookbook' in err
        assert 'END (PASS) - Cookbook cookbook (exit_code=0)' in err

    def test_main_execute_cookbook_ko(self, tmpdir, capsys):
        """Calling execute_cookbook() should return the exit status of the cookbook."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['group3.non_zero_exit'])

        _, err = capsys.readouterr()
        assert ret == 1
        assert 'END (FAIL) - Cookbook group3.non_zero_exit (exit_code=1)' in err

    def test_main_execute_cookbook_non_existent(self, tmpdir, capsys):
        """Calling execute_cookbook() with a non existent cookbook should return COOKBOOK_NOT_FOUND_RETCODE."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['non_existent'])

        _, err = capsys.readouterr()
        assert ret == cookbook.COOKBOOK_NOT_FOUND_RETCODE
        assert 'Unable to find cookbook' in err

    @pytest.mark.parametrize('module, error, code, args', (
        ('invalid_syntax', 'invalid syntax (invalid_syntax.py, line 7)', cookbook.COOKBOOK_NOT_FOUND_RETCODE, []),
        ('keyboard_interrupt', 'Ctrl+c pressed', cookbook.COOKBOOK_INTERRUPTED_RETCODE, []),
        ('raise_exception', 'Exception: Something went wrong', cookbook.COOKBOOK_EXCEPTION_RETCODE, []),
        ('raise_system_exit_0', 'SystemExit(0) raised', 0, []),
        ('raise_system_exit_0', 'SystemExit(0) raised by argparse -h/--help', 0, ['-h']),
        ('raise_system_exit_9', 'SystemExit(9) raised', 9, []),
        ('raise_system_exit_str', "SystemExit('message') raised", cookbook.COOKBOOK_EXCEPTION_RETCODE, []),
    ))  # pylint: disable=too-many-arguments
    def test_main_execute_cookbook_raise(self, tmpdir, capsys, module, error, code, args):
        """Calling execute_cookbook() should intercept any exception raised."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['group3.{name}'.format(name=module)] + args)

        _, err = capsys.readouterr()
        assert ret == code
        assert error in err

    def test_main_execute_dry_run(self, capsys, tmpdir):
        """Calling main() with a cookbook and dry_run mode should execute it and set the dry run mode."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack_dry_run):
                ret = cookbook.main(['-d', 'root'])

        assert ret == 0
        _, err = capsys.readouterr()
        assert 'DRY-RUN' in err

    def test_main_list(self, tmpdir, capsys):
        """Calling main() with the -l/--list option should print the available cookbooks."""
        config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
        with mock.patch('spicerack.cookbook.load_yaml_config', lambda config_dir: config):
            with mock.patch('spicerack.cookbook.Spicerack', return_value=self.spicerack):
                ret = cookbook.main(['-l'])

        out, err = capsys.readouterr()

        assert ret == 0
        assert out == LIST_COOKBOOKS_ALL
        lines = ['Failed to import module cookbooks.group3.invalid_syntax: invalid syntax (invalid_syntax.py, line 7)',
                 'Failed to import module cookbooks.group3.invalid_subgroup: invalid syntax (__init__.py, line 2)']
        for line in lines:
            assert line in err

    def test_cookbooks_menu_status(self, monkeypatch):
        """Calling status on a CookbooksMenu should show the completed and total tasks."""
        monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
        cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [], self.spicerack)
        menu = cookbooks.get_item(cookbooks.cookbooks_module_prefix)
        assert menu.status == '0/13'

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
         COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN.replace('args=[], verbose', "args=['--argument', 'value'], verbose") +
         COOKBOOKS_MENU_TTY.replace('[0/3] group2', '[1/3] group2')),
        (True, ['group2 -k', 'cookbook2', 'b', 'q'],
         COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP2_MENU.replace('args=[] ---', "args=['-k'] ---") +
         COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN.replace('args=[]', "args=['-k']") +
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
