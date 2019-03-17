"""Cookbook module."""
import argparse
import importlib
import logging
import os
import shlex
import sys

from abc import abstractmethod
from typing import Dict, List, Optional, Tuple, Type, Union

from spicerack import log, Spicerack
from spicerack.config import load_yaml_config
from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
COOKBOOK_NO_PARSER_WITH_ARGS_RETCODE = 95
"""int: reserved exit code: the cookbook doesn't have an argument_parser() function but was called with arguments."""
COOKBOOK_PARSE_ARGS_FAIL_RETCODE = 96
"""int: reserved exit code: the cookbook fail to parse arguments."""
COOKBOOK_INTERRUPTED_RETCODE = 97
"""int: reserved exit code: the execution was interrupted."""
COOKBOOK_NOT_FOUND_RETCODE = 98
"""int: reserved exit code: no cookbook is found for the selection."""
COOKBOOK_EXCEPTION_RETCODE = 99
"""int: reserved exit code: the cookbook raised an exception while executing."""
COOKBOOKS_MENU_HELP_MESSAGE = """Cookbooks interactive menu help

Available cookbooks and cookbook groups are shown in the menu with the format:
  [STATUS] NAME: DESCRIPTION
Additional control commands are also shown.
To select an item just input its name and press Enter.

Group of cookbooks:
  They have a status that represent the number of the executed cookbooks over
  the total number of cookbooks in that group and its child groups
  (i.e. [2/11]) or the status 'DONE' in case all cookbooks in that group were
  executed during the current session.
  When selected the child cookbooks group is shown.

Single cookbooks:
  Their status has one of the following values:
  {statuses}
  When selected the cookbook is executed and then the current menu is shown
  again after its execution, with the status updated based on the result of the
  execution.

Control commands:
  b: shown when inside a child group of cookbooks to go back one level to the
     parent menu.
  q: shown when at the top level of the current session menu to exit the
     program.
  h: always shown, print this help message.

  Note: 'q' and 'b' are mutually exclusive, only one of them is shown.

CLI arguments:
  It's possible to pass CLI parameters to cookbooks and group of cookbooks
  when selecting them (e.g. cookbook_name -a param value1 value2).
  Passing arguments to cookbook groups propagate them also to their cookbooks
  and child cookbook groups.
  Passing arguments override any other argument that might have been passed
  to the cookbook executable or to any of the parent groups when selected.

Interrupting execution:
  Pressing Ctrl+c/d while executing a cookbook interrupts it and show the
  current menu, marking the cookbook status as ERROR.
  Pressing Ctrl+c/d while in a menu is equivalent to select 'b' or 'q'.
"""
"""str: the generic CookbooksMenu help message, unformatted."""


class CookbookError(SpicerackError):
    """Custom exception class for errors of this module."""


class CookbooksModuleInterface:
    """Module interface to be used as type hint for the imported cookbooks."""

    __title__ = ''
    """str: the cookbook static title. Used if get_title() is not defined."""

    @staticmethod
    def argument_parser() -> argparse.ArgumentParser:
        """Optional module function to define if the cookbook should accept command line arguments."""

    @staticmethod
    def get_title(args: List[str]) -> str:
        """Optional module function to dynamically generate the cookbook's title. Has precedence over __title__."""

    @staticmethod
    def run(args: Optional[argparse.Namespace], spicerack: Spicerack) -> Optional[int]:
        """Mandatory module function that every cookbook must define with the cookbook's body."""


class Cookbooks:
    """Collect and represent available cookbooks."""

    cookbooks_module_prefix = 'cookbooks'

    def __init__(self, base_dir: str, args: List[str], spicerack: Spicerack, path_filter: Optional[str] = None) -> None:
        """Initialize the Cookbook class and collect CookbooksMenu and Cookbook items.

        Arguments:
            base_dir (str): the base directory from where to start looking for cookbooks.
            args (list): the list of arguments to pass to the collected items.
            spicerack (spicerack.Spicerack): the initialized instance of the library.
            path_filter (str, optional): an optional relative module path to filter for. If set, only cookbooks that
                are part of this subtree will be collected.
        """
        self.base_dir = os.path.join(base_dir, self.cookbooks_module_prefix)
        self.args = args
        self.spicerack = spicerack
        if path_filter is None:
            self.path_filter = path_filter
        else:
            self.path_filter = '.'.join((self.cookbooks_module_prefix, path_filter))

        self.menu = CookbooksMenu(self.cookbooks_module_prefix, self.args, self.spicerack)
        self._collect()

    def get_item(self, path: str) -> Optional[Union['CookbooksMenu', 'Cookbook']]:
        """Retrieve the item for a given path.

        Arguments:
            path (str): the path of the item to look for.

        Returns:
            None: when no item is found.
            spicerack.cookbook.CookbooksMenu: when the item found is a menu of cookbooks.
            spicerack.cookbook.Cookbook: when the item found is a single cookbook.

        """
        item = None
        progressive_path = []
        for i, subpath in enumerate(path.split('.')):
            progressive_path.append(subpath)
            if i == 0:
                item = self.menu
            elif item is not None and subpath in item.items.keys():
                item = item.items[subpath]
            else:
                item = None

        return item

    def _create_menu_for_path(self, path: str) -> 'CookbooksMenu':
        """Create the menu for a given path, including intermediate levels, if missing. Return the existing one if any.

        Arguments:
            path (str): the path of the item to look for.

        Returns:
            spicerack.cookbook.CookbooksMenu: the existing or created menu.

        """
        item = self.menu
        if path == self.cookbooks_module_prefix:
            return item

        progressive_path = [self.cookbooks_module_prefix]
        for subpath in path.split('.')[1:]:
            progressive_path.append(subpath)
            if item is not None and subpath in item.items.keys():
                item = item.items[subpath]
            else:
                module_name = '.'.join(progressive_path)
                submenu = CookbooksMenu(module_name, self.args, self.spicerack)
                item.append(submenu, add_parent=self._submenu_add_parent(module_name, path))
                item = submenu

        return item

    def _submenu_add_parent(self, module_name: str, path: str) -> bool:
        """Determine if the submenu item to be appended should have a link to the parent menu or not.

        When collecting the cookbooks and creating the CookbooksMenu instances, the relation to the parent menu should
        be skipped for those intermediate menus created for coherence but that should not be accessible by the user,
        like when using a path_filter.

        Arguments:
            module_name (str): the module name of the submenu.
            path (str): of the item to be add.

        Returns:
            bool: True if the link to the parent menu should be set, False otherwise.

        """
        if module_name != path:
            return False

        if self.path_filter is None:
            return True

        return path.startswith(self.path_filter) and len(path) > len(self.path_filter)

    @staticmethod
    def _filter_dirnames_and_filenames(dirnames: List[str], filenames: List[str]) -> Tuple[List, List]:
        """Filter the dirnames and filenames in place (required by os.walk()) to select only Python modules.

        Arguments:
            dirnames (list): the list of sub-directories, as returned by os.walk().
            filenames (list): the list of filenames in the current directory, as returned by os.walk().

        Returns:
            tuple: (list, list) with the modified dirnames and filenames.

        """
        try:
            dirnames.remove('__pycache__')
        except ValueError:
            pass

        for filename in filenames.copy():
            if filename == '__init__.py' or not filename.endswith('.py'):
                filenames.remove(filename)

        return dirnames, filenames

    def _collect(self) -> None:
        """Collect available cookbooks starting from a base path."""
        for dirpath, dirnames, filenames in os.walk(self.base_dir):
            dirnames, filenames = Cookbooks._filter_dirnames_and_filenames(dirnames, filenames)
            if not filenames and not dirnames:
                continue

            # Sort the directories and files to be recursed in-place, required by os.walk().
            dirnames.sort()
            filenames.sort()

            relpath = os.path.relpath(dirpath, start=self.base_dir)
            prefix = self.cookbooks_module_prefix
            if relpath != '.':
                prefix = '.'.join((self.cookbooks_module_prefix, relpath.replace('/', '.')))

            if (self.path_filter is not None and not prefix.startswith(self.path_filter) and
                    sum('.'.join((prefix, filename)).startswith(self.path_filter) for filename in filenames) == 0):
                continue

            path = prefix.rstrip('.')
            try:
                menu = self._create_menu_for_path(path)
            except CookbookError as e:
                logger.error(e)
                continue

            for filename in filenames:
                self._collect_filename(filename, prefix, menu)

    def _collect_filename(self, filename: str, prefix: str, menu: 'CookbooksMenu') -> None:
        """Iterate the filenames in the current directory as reported by os.walk() and add them to the tree.

        Arguments:
            filename (str): the filename to collect.
            prefix (str): the Python module prefix to use to load the given filename.
            menu (spicerack.cookbook.CookbooksMenu): the menu to append the collected cookbook to.

        """
        cookbook_module_name = '.'.join((prefix, os.path.splitext(filename)[0]))
        if self.path_filter is not None and not cookbook_module_name.startswith(self.path_filter):
            return

        try:
            cookbook = Cookbook(cookbook_module_name, self.args, self.spicerack)
        except CookbookError as e:
            logger.error(e)
            return

        menu.append(cookbook)


class BaseCookbooksItem:
    """Base class for any item collected by the Cookbooks class."""

    fallback_title = '-'

    def __init__(self, module_name: str, args: List[str], spicerack: Spicerack) -> None:
        """Base cookbooks's item constructor.

        Arguments:
            module_name (str): the Python module to load.
            args (list): the command line arguments to pass to the item.
            spicerack (spicerack.Spicerack): the initialized instance of the library.
        """
        if '.' in module_name:
            self.name = module_name.rsplit('.', 1)[1]
            self.path = module_name.split('.', 1)[1]
        else:
            self.name = module_name
            self.path = module_name

        self.module = import_module(module_name)
        self.args = args
        self.spicerack = spicerack
        self.title = self._get_title()

    @abstractmethod
    def run(self) -> int:
        """Excecute the item."""

    @property
    def verbose_title(self) -> str:
        """Getter for the verbose_title property, uses the module name if there is no title.

        Returns:
            str: the verbose title of the item.

        """
        if self.title != self.fallback_title:
            return self.title

        return self.name

    def _get_title(self) -> str:
        """Calculate the title of the instance item.

        Returns:
            str: the title of the item.

        """
        try:
            if hasattr(self.module, 'get_title'):
                title = self.module.get_title(self.args)
            else:
                title = self.module.__title__
        except Exception as e:  # pylint: disable=broad-except
            logger.debug('Unable to detect title for module %s: %s', self.path, e)
            title = self.fallback_title

        return title

    @staticmethod
    def _get_line_prefix(level: int, cont_levels: List[bool], is_final: bool) -> str:
        """Return the line prefix for the given level in the tree.

        Arguments:
            level (int): how many levels the item is nested in the tree.
            cont_levels (list): a list of size levels with booleans that indicate for each level if the
                continuation prefix (True) or an empty prefix (False) should be used.
            is_final (bool): whether the line is the final in its own group.

        Returns:
            str: the line prefix to use.

        """
        empty_sep = '    '
        cont_sep = '|   '

        if is_final:
            base_sep = '`-- '
        else:
            base_sep = '|-- '

        if level == 0:
            return base_sep

        levels = []
        for cont_level in cont_levels:
            if cont_level:
                levels.append(cont_sep)
            else:
                levels.append(empty_sep)

        return ''.join(levels) + base_sep


class Cookbook(BaseCookbooksItem):
    """Cookbook class."""

    fallback_title = 'UNKNOWN (unable to detect title)'
    statuses = ('NOTRUN', 'PASS', 'FAIL', 'ERROR')  # Status labels
    not_run, success, failed, error = statuses  # Valid statuses variables

    def __init__(self, module_name: str, args: List[str], spicerack: Spicerack) -> None:
        """Override parent constructor to add menu-specific initialization.

        :Parameters:
            according to spicerack.cookbook.BaseCookbooksItem.
        """
        super().__init__(module_name, args, spicerack)
        self.status = Cookbook.not_run

    def run(self) -> int:
        """Run the cookbook, calling both its `argument_parser` and `run` functions.

        Returns:
            int: the return code to use for this cookbook, it should be zero on success, a positive integer smaller than
            128 and not in the range 90-99 (reserved exit codes) in case of failure.

        """
        ret, args = self._parse_args()
        if ret != -1:
            return ret

        return self._run(args)

    def _run(self, args: Optional[argparse.Namespace]) -> int:
        """Run the cookbook's `run()` function.

        Arguments:
            args (argparse.Namespace, None): the parsed arguments or None if the cookbook doesn't define a
                `argument_parser()` function.

        Returns:
            int: the return code to use for this cookbook, it should be zero on success, a positive integer smaller than
            128 and not in the range 90-99 (reserved exit codes) in case of failure.

        """
        log.log_task_start('Cookbook ' + self.path)
        message = 'raised while executing cookbook'

        try:
            ret = self.module.run(args, self.spicerack)
            if ret is None:
                ret = 0
        except KeyboardInterrupt:
            logger.error('Ctrl+c pressed')
            self.status = Cookbook.error
            ret = COOKBOOK_INTERRUPTED_RETCODE
        except SystemExit as e:
            if isinstance(e.code, int):
                ret = e.code
                if e.code == 0:
                    logger.info('SystemExit(0) %s %s, assuming success:', message, self.path)
                    self.status = Cookbook.success
                else:
                    logger.exception('SystemExit(%d) %s %s:', e.code, message, self.path)
                    self.status = Cookbook.error
            else:
                logger.exception("SystemExit('%s') %s %s:", e.code, message, self.path)
                self.status = Cookbook.error
                ret = COOKBOOK_EXCEPTION_RETCODE
        except BaseException:
            logger.exception('Exception %s %s:', message, self.path)
            self.status = Cookbook.failed
            ret = COOKBOOK_EXCEPTION_RETCODE
        else:
            self.status = Cookbook.success if ret == 0 else Cookbook.failed

        log.log_task_end(self.status, 'Cookbook {name} (exit_code={ret})'.format(
            name=self.path, ret=ret))

        return ret

    def _parse_args(self) -> Tuple[int, Optional[argparse.Namespace]]:
        """Get the argument parser from the cookbook, if it exists, and parse the arguments.

        Returns:
            tuple: (int, argparse.Namespace) with the return code to use and the parsed arguments. If the return code is
            different from -1 it means that the cookbook should not be executed either because the help message was
            requested or the parse of the arguments failed or arguments were passed but the cookbook doesn't define
            a argument_parser() function.

        """
        ret = -1
        args = None
        message = 'raised while parsing arguments for cookbook'

        if not hasattr(self.module, 'argument_parser'):
            if self.args:
                ret = COOKBOOK_NO_PARSER_WITH_ARGS_RETCODE

            return ret, args

        try:
            args = self.module.argument_parser().parse_args(self.args)
        except SystemExit as e:
            if isinstance(e.code, int):
                ret = e.code
            else:
                logger.exception("SystemExit('%s') %s %s:", e.code, message, self.path)
                ret = COOKBOOK_PARSE_ARGS_FAIL_RETCODE
        except BaseException:
            logger.exception('Exception %s %s:', message, self.path)
            ret = COOKBOOK_PARSE_ARGS_FAIL_RETCODE

        return ret, args


class CookbooksMenu(BaseCookbooksItem):
    """Cookbooks Menu class."""

    back_answer = 'b'
    """str: interactive menu answer to go back to the parent menu."""
    help_answer = 'h'
    """str: interactive menu answer to print the generic CookbooksMenu help message."""
    quit_answer = 'q'
    """str: answer to quit the interactive menu."""
    help_message = COOKBOOKS_MENU_HELP_MESSAGE.format(statuses=Cookbook.statuses)
    """str: the generic CookbooksMenu help message."""

    def __init__(self, module_name: str, args: List[str], spicerack: Spicerack) -> None:
        """Override parent constructor to add menu-specific initialization.

        :Parameters:
            according to spicerack.cookbook.BaseCookbooksItem.
        """
        super().__init__(module_name, args, spicerack)
        self.parent = None  # type: Optional[CookbooksMenu]
        self.items = {}  # type: ignore

    @property
    def status(self) -> str:
        """Getter for the menu status, returns a string representation of the status of its tasks.

        Returns:
            str: the menu status message.

        """
        completed, total = self.calculate_status()
        if completed == total:
            message = 'DONE'
        else:
            message = '{completed}/{total}'.format(completed=completed, total=total)

        return message

    def append(self, item: Union['CookbooksMenu', Cookbook], add_parent: bool = True) -> None:
        """Append an item to this menu.

        Arguments:
            item (spicerack.cookbook.Cookbook, spicerack.cookbook.CookbooksMenu): the item to append.
            add_parent (bool, optional): wheter to set the parent of the new item to the current instance.
        """
        if add_parent and isinstance(item, CookbooksMenu):
            item.parent = self

        self.items[item.name] = item

    def run(self) -> int:
        """Execute the menu in an interactive way (infinite loop).

        Returns:
            int: being an interactive menu it always returns 0.

        """
        try:
            while True:
                self.run_once()
        except StopIteration:
            pass

        return 0

    def show(self) -> None:
        """Print the menu to stdout."""
        for name in sorted(self.items.keys()):
            item = self.items[name]
            print('[{status}] {name}: {title}'.format(status=item.status, name=name, title=item.title))

        if self.parent is None:
            print('{answer} - Quit'.format(answer=CookbooksMenu.quit_answer))
        else:
            print('{answer} - Back to parent menu'.format(answer=CookbooksMenu.back_answer))

        print('{answer} - Help'.format(answer=CookbooksMenu.help_answer))

    def calculate_status(self) -> Tuple[int, int]:
        """Calculate the status of a menu, checking the status of all it's tasks recursively.

        Returns:
            tuple: (int, int) with the number of completed and total items.

        """
        completed = 0
        total = 0
        for item in self.items.values():
            if isinstance(item, CookbooksMenu):
                sub_completed, sub_total = item.calculate_status()
                completed += sub_completed
                total += sub_total
            elif isinstance(item, Cookbook):
                total += 1
                if item.status != Cookbook.not_run:
                    completed += 1
            else:  # pragma: no cover | This should never happen
                raise CookbookError('Unknown item of type {type}'.format(type=type(item)))

        return completed, total

    def get_tree(self) -> str:
        """Return the tree representation of the menu as string.

        Returns:
            str: the tree representation of all the collected items.

        """
        lines = self.get_menu_tree(0, [])
        if not lines:
            return ''

        return '{title}\n{lines}\n'.format(title=Cookbooks.cookbooks_module_prefix, lines='\n'.join(lines))

    def get_menu_tree(self, level: int, cont_levels: List[bool]) -> List[str]:
        """Calculate the tree lines for a given menu.

        Arguments:
            level (int): how many levels the item is nested in the tree.
            cont_levels (list): a list of size levels with booleans that indicate for each level if the
                continuation prefix (True) or an empty prefix (False) should be used.

        Returns:
            list: the list of lines that represent the tree.

        """
        lines = []
        for i, key in enumerate(sorted(self.items.keys())):
            is_final = (i == len(self.items) - 1)
            name = self.items[key].path
            prefix = self._get_line_prefix(level, cont_levels, is_final)

            if self.spicerack.verbose:
                line = '{prefix}{name}: {title}'.format(prefix=prefix, name=name, title=self.items[key].title)
            else:
                line = '{prefix}{name}'.format(prefix=prefix, name=name)

            lines.append(line)

            if isinstance(self.items[key], CookbooksMenu):
                lines += self.items[key].get_menu_tree(level + 1, cont_levels + [not is_final])

        return lines

    def run_once(self) -> None:
        """Run the menu in an interactive way.

        Returns:
            spicerack.cookbook.CookbooksMenu: the current menu instance.

        """
        print('#--- {title} args={args} ---#'.format(title=self.verbose_title, args=self.args))
        self.show()

        if not sys.stdout.isatty():
            print('Not a tty, exiting.')
            raise StopIteration

        try:
            answer = input('>>> ')
        except (EOFError, KeyboardInterrupt):
            print('QUIT')
            raise StopIteration  # Ctrl+d or Ctrl+c pressed while waiting for input

        if not answer:
            return

        if answer == CookbooksMenu.help_answer:
            print(self.help_message)
            return

        if answer == CookbooksMenu.quit_answer and self.parent is None:
            raise StopIteration

        if answer == CookbooksMenu.back_answer and self.parent is not None:
            raise StopIteration

        name, *args = shlex.split(answer)
        if name not in self.items.keys():
            print('==> Invalid input <==')
            return

        item = self.items[name]
        item.args = self._get_item_args(item, args)
        item.run()

    def _get_item_args(self, item: Type[BaseCookbooksItem], args: List[str]) -> List[str]:
        """Get the arguments to pass to the given item.

        Arguments:
            item (spicerack.cookbook.BaseCookbooksItem): the item to pass the arguments to.
            args (list): the arguments passed via interactive menu to this item.

        Returns:
            list: the arguments to pass to the item.

        """
        if args:  # Override the item arguments with the ones passed interactively, if any.
            return args

        if self.args:  # Override the item arguments with the ones of the menu, if any.
            return self.args

        return item.args


def argument_parser() -> argparse.ArgumentParser:
    """Get the CLI argument parser.

    If the COOKBOOK is passed as a path, it will be converted to a Python module syntax.

    Returns:
        argparse.ArgumentParser: the argument parser instance.

    """
    parser = argparse.ArgumentParser(description='Spicerack Cookbook Runner')
    parser.add_argument(
        '-l', '--list', action='store_true',
        help=('List all available cookbooks, if -v/--verbose is set print also their description. If a COOKBOOK is '
              'also specified, it will be used as a prefix filter.'))
    parser.add_argument('-c', '--config-file', default='/etc/spicerack/config.yaml',
                        help='Path to the Spicerack configuration file to load.')
    parser.add_argument('-d', '--dry-run', action='store_true', help='Set the DRY-RUN mode, also for the cookbook.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output, also for the cookbook.')
    parser.add_argument(
        'cookbook', metavar='COOKBOOK', nargs='?', type=cookbook_path_type,
        help=('Either a relative path of the Python file to execute (group/cookbook.py) or the name of the Python '
              'module to execute (group.cookbook). If the selected path/module is a directory or is not set, an '
              'interactive menu will be shown.'))
    parser.add_argument(
        'cookbook_args', metavar='COOKBOOK_ARGS', nargs=argparse.REMAINDER,
        help='Collect all the remaining arguments to be passed to the cookbook or menu to execute.')

    return parser


def cookbook_path_type(path: str) -> str:
    """Convert a COOKBOOK path to module syntax, if it's in path syntax.

    Arguments:
        path (str): the path to be converted.

    Returns:
        str: the converted path in module syntax.

    """
    cookbook_path, ext = os.path.splitext(path)
    if ext == '.py':
        path = cookbook_path.replace('/', '.')

    return path


def import_module(module_name: str) -> CookbooksModuleInterface:
    """Import a Python module.

    Arguments:
        module_name (str): the name of the module to load.

    Returns:
        types.ModuleType: the loaded module, that must respect the CookbooksModuleInterface.

    Raises:
        spicerack.cookbook.CookbookError: on failure to load the module.

    """
    try:
        return importlib.import_module(module_name)  # type: ignore
    except Exception as e:  # pylint: disable=broad-except
        raise CookbookError('Failed to import module {name}: {msg}'.format(name=module_name, msg=e)) from e


def execute_cookbook(config: Dict[str, str], args: argparse.Namespace, cookbooks: Cookbooks) -> int:
    """Execute a single cookbook with its parameters.

    Arguments:
        config (dict): the configuration dictionary.
        args (argparse.Namespace): the parsed arguments.
        cookbooks (spicerack.cookbook.Cookbooks): the collected cookbooks.

    Returns:
        int: the return code, 0 on success, non-zero on cookbook failure, 98 on cookbook exception.

    """
    if args.cookbook is not None:
        path = '.'.join((Cookbooks.cookbooks_module_prefix, args.cookbook))
    else:
        path = Cookbooks.cookbooks_module_prefix

    cookbook = cookbooks.get_item(path)
    if cookbook is None:
        logger.error('Unable to find cookbook %s', args.cookbook)
        return COOKBOOK_NOT_FOUND_RETCODE

    cookbook_path, cookbook_name = os.path.split(cookbook.path.replace('.', os.sep))
    base_path = os.path.join(config['logs_base_dir'], cookbook_path)
    log.setup_logging(base_path, cookbook_name, cookbooks.spicerack.username, dry_run=args.dry_run,
                      host=config.get('tcpircbot_host', None), port=int(config.get('tcpircbot_port', 0)))

    logger.debug('Executing cookbook %s with args: %s', args.cookbook, args.cookbook_args)
    return cookbook.run()


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point, run the tool.

    Arguments:
        argv (list, optional): the list of command line arguments to parse.

    Returns:
        int: the return code, zero on success, non-zero on failure.

    """
    args = argument_parser().parse_args(argv)
    config = load_yaml_config(args.config_file)
    sys.path.append(config['cookbooks_base_dir'])

    spicerack = Spicerack(verbose=args.verbose, dry_run=args.dry_run)
    cookbooks = Cookbooks(config['cookbooks_base_dir'], args.cookbook_args, spicerack, path_filter=args.cookbook)

    if args.list:
        print(cookbooks.menu.get_tree(), end='')
        return 0

    return execute_cookbook(config, args, cookbooks)
