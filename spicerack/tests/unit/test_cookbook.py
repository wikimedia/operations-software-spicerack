"""Cookbook module tests."""
import os
import shutil

from unittest import mock

import pytest

from spicerack import cookbook


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
|   |-- group3.non_zero_exit
|   |-- group3.raise_exception
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
|   |-- group3.non_zero_exit: Group3 Non-Zero return code
|   |-- group3.raise_exception: Group3 Raise Exception Cookbook
|   `-- group3.subgroup3: -
|       `-- group3.subgroup3.cookbook4: Group3 Subgroup3 Cookbook4
`-- root: Top level cookbook: []
"""
LIST_COOKBOOKS_GROUP3 = """cookbooks
`-- group3
    |-- group3.non_zero_exit
    |-- group3.raise_exception
    `-- group3.subgroup3
        `-- group3.subgroup3.cookbook4
"""
LIST_COOKBOOKS_GROUP3_SUBGROUP3 = """cookbooks
`-- group3
    `-- group3.subgroup3
        `-- group3.subgroup3.cookbook4
"""
COOKBOOKS_MENU_TTY = """#--- cookbooks ---#
[NOTRUN] cookbook: Top level cookbook
[0/1] group1: Group1 Test Cookbooks
[0/3] group2: -
[0/3] group3: -
[NOTRUN] root: Top level cookbook: []
q - Quit
"""
COOKBOOKS_MENU_NOTTY = """#--- cookbooks ---#
[NOTRUN] cookbook: Top level cookbook
[0/1] group1: Group1 Test Cookbooks
[0/3] group2: -
[0/3] group3: -
[NOTRUN] root: Top level cookbook: []
q - Quit
Not a tty, exiting.
"""
COOKBOOKS_GROUP2_MENU = """#--- group2 ---#
[NOTRUN] cookbook2: Group2 Cookbook2
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
"""
COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN = """args=[], verbose=False, dry_run=False
#--- group2 ---#
[PASS] cookbook2: Group2 Cookbook2
[0/1] subgroup1: -
[NOTRUN] zcookbook4: UNKNOWN (unable to detect title)
b - Back to parent menu
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


@pytest.mark.parametrize('options, expected', (
    ({}, LIST_COOKBOOKS_ALL),
    ({'verbose': True}, LIST_COOKBOOKS_ALL_VERBOSE),
    ({'path_filter': 'group3'}, LIST_COOKBOOKS_GROUP3),
    ({'path_filter': 'group3.subgroup3'}, LIST_COOKBOOKS_GROUP3_SUBGROUP3),
    ({'path_filter': 'group3.non_existent'}, ''),
))
def test_cookbooks_str(monkeypatch, options, expected):
    """The string representation of the Cookbooks should print all the cookbooks as a tree, based on the options."""
    monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
    if not options:  # For the first test ensure there is no __pycache__ directory in one case.
        shutil.rmtree(os.path.join(COOKBOOKS_BASE_PATH, 'cookbooks', '__pycache__'), ignore_errors=True)

    cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [], **options)
    assert cookbooks.menu.get_tree() == expected


def test_cookbooks_non_existent():
    """The Cookbooks class initialized with an empty path should not collect any cookbook."""
    cookbooks = cookbook.Cookbooks(os.path.join(COOKBOOKS_BASE_PATH, 'non_existent'), [])
    assert cookbooks.menu.get_tree() == ''


def test_main_execute_cookbook_ok(tmpdir, capsys):
    """Calling main() with a cookbook should run the cookbook."""
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main(['cookbook'])

    _, err = capsys.readouterr()
    assert ret == 0
    assert 'START - Cookbook cookbook' in err
    assert 'END (PASS) - Cookbook cookbook (exit_code=0)' in err


def test_main_execute_cookbook_ko(tmpdir, capsys):
    """Calling execute_cookbook() should return the exit status of the cookbook."""
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main(['group3.non_zero_exit'])

    _, err = capsys.readouterr()
    assert ret == 1
    assert 'END (FAIL) - Cookbook group3.non_zero_exit (exit_code=1)' in err


def test_main_execute_cookbook_non_existent(tmpdir, capsys):
    """Calling execute_cookbook() with a non existent cookbook should return COOKBOOK_NOT_FOUND_RETCODE."""
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main(['non_existent'])

    _, err = capsys.readouterr()
    assert ret == cookbook.COOKBOOK_NOT_FOUND_RETCODE
    assert 'Unable to find cookbook' in err


@pytest.mark.parametrize('module, error, code', (
    ('invalid_syntax', 'invalid syntax (invalid_syntax.py, line 7)', cookbook.COOKBOOK_NOT_FOUND_RETCODE),
    ('raise_exception', 'Exception: Something went wrong', cookbook.COOKBOOK_EXCEPTION_RETCODE),
))
def test_main_execute_cookbook_raise(tmpdir, capsys, module, error, code):
    """Calling execute_cookbook() should intercept any exception raised."""
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main(['group3.{name}'.format(name=module)])

    _, err = capsys.readouterr()
    assert ret == code
    assert error in err


def test_main_execute_dry_run(capsys, tmpdir):
    """Calling main() with a cookbook and dry_run mode should execute it and set the dry run mode."""
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main(['-d', 'root'])

    assert ret == 0
    _, err = capsys.readouterr()
    assert 'DRY-RUN' in err


def test_main_list(tmpdir, capsys):
    """Calling main() with the -l/--list option should print the available cookbooks."""
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main(['-l'])

    out, err = capsys.readouterr()
    assert ret == 0
    assert out == LIST_COOKBOOKS_ALL
    assert 'Failed to import module cookbooks.group3.invalid_syntax: invalid syntax (invalid_syntax.py, line 7)' in err
    assert 'Failed to import module cookbooks.group3.invalid_subgroup: invalid syntax (__init__.py, line 2)' in err


def test_cookbooks_menu_status(monkeypatch):
    """Calling status on a CookbooksMenu should show the completed and total tasks."""
    monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
    cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [])
    menu = cookbooks.get_item(cookbooks.cookbooks_module_prefix)
    assert menu.status == '0/9'


def test_cookbooks_menu_status_done(monkeypatch):
    """Calling status on a CookbooksMenu with all tasks completed should return DONE."""
    monkeypatch.syspath_prepend(COOKBOOKS_BASE_PATH)
    cookbooks = cookbook.Cookbooks(COOKBOOKS_BASE_PATH, [], path_filter='group1')
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
    (True, ['group2', 'b', 'q'], COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP2_MENU + COOKBOOKS_MENU_TTY),
    (True, ['group2', 'cookbook2', 'b', 'q'],
     COOKBOOKS_MENU_TTY + COOKBOOKS_GROUP2_MENU + COOKBOOKS_GROUP2_COOKBOOK2_MENU_RUN + COOKBOOKS_MENU_TTY.replace(
        '[0/3] group2', '[1/3] group2')),
))
@mock.patch('spicerack.cookbook.sys.stdout.isatty')
@mock.patch('builtins.input')    # pylint: disable=too-many-arguments
def test_cookbooks_main_menu(mocked_input, mocked_tty, tty, answer, output, capsys, tmpdir):
    """Calling main() with a menu should show the menu and allow to interact with it."""
    mocked_tty.return_value = tty
    mocked_input.side_effect = answer
    config = {'cookbooks_base_dir': COOKBOOKS_BASE_PATH, 'logs_base_dir': tmpdir.strpath}
    with mock.patch('spicerack.cookbook.get_global_config', lambda: config):
        ret = cookbook.main([])

    out, _ = capsys.readouterr()
    assert ret == 0
    assert out == output
