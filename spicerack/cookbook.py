"""Cookbook module."""
import argparse
import importlib
import logging
import os
import sys

from spicerack import log, Spicerack
from spicerack.config import get_global_config
from spicerack.exceptions import SpicerackError


COOKBOOK_NOT_FOUND_RETCODE = 98
COOKBOOK_EXCEPTION_RETCODE = 99
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class CookbookError(SpicerackError):
    """Custom exception class for errors of this module."""


class Cookbooks:
    """Collect and represent available cookbooks."""

    cookbooks_module_prefix = 'cookbooks'

    def __init__(self, base_dir, args, spicerack, path_filter=None):
        """Initialize the Cookbook class and collect CookbooksMenu and Cookbook items.

        Arguments:
            base_dir (str): the base directory from where to start looking for cookbooks.
            args (list, tuple): the list of arguments to pass to the collected items.
            spicerack (spicerack.Spicerack): the initialized instance of the library.
            path_filter (str, optional): an optional relative module path to filter for. If set, only cookbooks that
                are part of this subtree will be collected.
        """
        self.base_dir = os.path.join(base_dir, self.cookbooks_module_prefix)
        self.args = args
        self.spicerack = spicerack
        if path_filter is not None:
            self.path_filter = '.'.join((self.cookbooks_module_prefix, path_filter))
        else:
            self.path_filter = path_filter

        self.menu = CookbooksMenu(self.cookbooks_module_prefix, self.args, self.spicerack)
        self._collect()

    def get_item(self, path):
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

    def _create_menu_for_path(self, path):
        """Create the menu for a given path, if missing. Return the existing one if any.

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
                add_parent = (module_name == path and self.path_filter is None)
                item.append(submenu, add_parent=add_parent)
                item = submenu

        return item

    @staticmethod
    def _filter_dirnames_and_filenames(dirnames, filenames):
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

    def _collect(self):
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

    def _collect_filename(self, filename, prefix, menu):
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

    def __init__(self, module_name, args, spicerack):
        """Base cookbooks's item constructor.

        Arguments:
            module_name (str): the Python module to load.
            args (list, tuple): the command line arguments to pass to the item.
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

    def _get_title(self):
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
    def _get_line_prefix(level, cont_levels, is_final):
        """Return the line prefix for the given level in the tree.

        Arguments:
            level (int): how many levels the item is nested in the tree.
            cont_levels (list, tuple): an iterable of size levels with booleans that indicate for each level if the
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


class CookbooksMenu(BaseCookbooksItem):
    """Cookbooks Menu class."""

    def __init__(self, module_name, args, spicerack):
        """Override parent constructor to add menu-specific initialization.

        :Parameters:
            according to spicerack.cookbook.BaseCookbooksItem.
        """
        super().__init__(module_name, args, spicerack)
        self.parent = None
        self.items = {}

    @property
    def status(self):
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

    def append(self, item, add_parent=True):
        """Append an item to this menu.

        Arguments:
            item (spicerack.cookbook.Cookbook, spicerack.cookbook.CookbooksMenu): the item to append.
            add_parent (bool, optional): wheter to set the parent of the new item to the current instance.
        """
        if add_parent and isinstance(item, CookbooksMenu):
            item.parent = self

        self.items[item.name] = item

    def run(self):
        """Excecute the menu in an interactive."""
        menu = self
        try:
            while True:
                menu = self._run(menu)
        except StopIteration:
            pass

        return 0

    def show(self):
        """Print the menu to stdout."""
        for name in sorted(self.items.keys()):
            item = self.items[name]
            print('[{status}] {name}: {title}'.format(status=item.status, name=name, title=item.title))

        if self.parent is None:
            print('q - Quit')
        else:
            print('b - Back to parent menu')

    def calculate_status(self):
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

    def get_tree(self):
        """Return the tree representation of the menu as string.

        Returns:
            str: the tree representation of all the collected items.

        """
        lines = self.get_menu_tree(0, [])
        if not lines:
            return ''

        return '{title}\n{lines}\n'.format(title=Cookbooks.cookbooks_module_prefix, lines='\n'.join(lines))

    def get_menu_tree(self, level, cont_levels):
        """Calculate the tree lines for a given menu.

        Arguments:
            level (int): how many levels the item is nested in the tree.
            cont_levels (list, tuple): an iterable of size levels with booleans that indicate for each level if the
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

    @staticmethod
    def _run(menu):
        """Run the menu in an interactive way.

        Arguments:
            menu (spicerack.cookbook.CookbooksMenu): the menu to execute.
        """
        print('#--- {title} ---#'.format(title=menu.title if menu.title != menu.fallback_title else menu.name))
        menu.show()

        if not sys.stdout.isatty():
            print('Not a tty, exiting.')
            raise StopIteration

        try:
            answer = input('>>> ')
        except (EOFError, KeyboardInterrupt):
            print('QUIT')
            raise StopIteration  # Ctrl+d or Ctrl+c pressed while waiting for input

        if not answer:
            return menu

        if answer == 'q' and menu.parent is None:
            raise StopIteration

        if answer == 'b' and menu.parent is not None:
            return menu.parent

        if answer not in menu.items.keys():
            print('==> Invalid input <==')
            return menu

        item = menu.items[answer]
        if isinstance(item, CookbooksMenu):
            return item

        if isinstance(item, Cookbook):
            item.run()
            return menu

        raise CookbookError('Unknown item of type {type}'.format(type=type(item)))  # pragma: no cover


class Cookbook(BaseCookbooksItem):
    """Cookbook class."""

    fallback_title = 'UNKNOWN (unable to detect title)'
    statuses = ('NOTRUN', 'PASS', 'FAIL')  # Status labels
    not_run, success, failed = statuses  # Valid statuses variables

    def __init__(self, module_name, args, spicerack):
        """Override parent constructor to add menu-specific initialization.

        :Parameters:
            according to spicerack.cookbook.BaseCookbooksItem.
        """
        super().__init__(module_name, args, spicerack)
        self.status = self.not_run

    def run(self):
        """Run the cookbook, calling its main() function.

        Return:
            int: the return code of the cookbook execution. Zero for success, non-zero for failure.

        """
        log.log_task_start('Cookbook ' + self.path)
        try:
            ret = self.module.main(self.args, self.spicerack)
        except Exception:  # pylint: disable=broad-except
            logger.exception('Exception raised while executing cookbook %s:', self.path)
            self.status = self.failed
            ret = COOKBOOK_EXCEPTION_RETCODE
        else:
            if ret == 0:
                self.status = self.success
            else:
                self.status = self.failed

        log.log_task_end(self.status, 'Cookbook {name} (exit_code={ret})'.format(
            name=self.path, ret=ret))

        return ret


def parse_args(argv):
    """Parse command line arguments and return them.

    If the COOKBOOK is passed as a path, it will be converted to a Python module syntax.

    Arguments:
        argv (list): the list of command line arguments to parse.

    Returns:
        argparse.Namespace: the parsed arguments.

    """
    parser = argparse.ArgumentParser(description='Spicerack Cookbook Runner')
    parser.add_argument(
        '-l', '--list', action='store_true',
        help=('List all available cookbooks, if -v/--verbose is set print also their description. If a COOKBOOK is '
              'also specified, it will be used as a prefix filter.'))
    parser.add_argument('-c', '--config-dir', default='/etc/spicerack',
                        help='Path to the Spicerack configuration directory.')
    parser.add_argument('-d', '--dry-run', action='store_true', help='Set the DRY-RUN mode, also for the cookbook.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output, also for the cookbook.')
    parser.add_argument(
        'cookbook', metavar='COOKBOOK', nargs='?', type=cookbook_path_type,
        help=('Either a relative path of the Python file to execute (group/cookbook.py) or the name of the Python '
              'module to execute (group.cookbook).'))
    parser.add_argument(
        'cookbook_args', metavar='COOKBOOK_ARGS', nargs=argparse.REMAINDER,
        help='Collect all the remaining arguments to be passed to the cookbook to execute.')

    args = parser.parse_args(args=argv)

    return args


def cookbook_path_type(path):
    """Convert a COOKBOOK path to module syntax, if it's in path syntax.

    Arguments:
        path (str, None): the path to be converted.

    Returns:
        str, None: the converted path in module syntax or None if None was passed.

    """
    cookbook_path, ext = os.path.splitext(path)
    if ext == '.py':
        path = cookbook_path.replace('/', '.')

    return path


def import_module(module_name):
    """Import a Python module.

    Arguments:
        module_name (str): the name of the module to load.

    Raises:
        spicerack.cookbook.CookbookError: on failure to load the module.

    """
    try:
        return importlib.import_module(module_name)
    except Exception as e:  # pylint: disable=broad-except
        raise CookbookError('Failed to import module {name}: {msg}'.format(name=module_name, msg=e)) from e


def execute_cookbook(config, args, cookbooks):
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
    log.setup_logging(base_path, cookbook_name, cookbooks.spicerack.user, dry_run=args.dry_run,
                      host=config.get('tcpircbot_host', None), port=config.get('tcpircbot_port', 0))

    logger.debug('Executing cookbook %s with args: %s', args.cookbook, args.cookbook_args)
    return cookbook.run()


def main(argv=None):
    """Entry point, run the tool.

    Arguments:
        argv (list, optional): the list of command line arguments to parse.

    Returns:
        int: the return code, zero on success, non-zero on failure.

    """
    args = parse_args(argv)
    config = get_global_config(config_dir=args.config_dir)
    sys.path.append(config['cookbooks_base_dir'])

    spicerack = Spicerack(verbose=args.verbose, dry_run=args.dry_run)
    cookbooks = Cookbooks(config['cookbooks_base_dir'], args.cookbook_args, spicerack, path_filter=args.cookbook)

    if args.list:
        print(cookbooks.menu.get_tree(), end='')
        return 0

    return execute_cookbook(config, args, cookbooks)
