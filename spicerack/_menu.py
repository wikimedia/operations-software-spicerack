"""Cookbook internal module."""
import argparse
import logging
import shlex
import sys
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, cast

from spicerack import Spicerack, _log, _module_api, cookbook
from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)
HELP_MESSAGE = """Cookbooks interactive menu help

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
  It's possible to pass CLI arguments to cookbooks and group of cookbooks
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
"""str: The generic TreeItem help message, unformatted."""


class MenuError(SpicerackError):
    """Custom exception class for errors of this module."""


class BaseItem:
    """Base class for any item collected by the CookbookCollection class."""

    fallback_title: str = "-"

    def __init__(self, args: Sequence[str], spicerack: Spicerack) -> None:
        """Base cookbooks's item constructor.

        Arguments:
            args (list): any sequence with the command line arguments to pass to the item.
            spicerack (spicerack.Spicerack): the initialized instance of the library.

        """
        self.args = args
        self.spicerack = spicerack
        self.name = ""
        self.path = ""  # Path of the cookbook in Spicerack terms, relative to the base directory
        self.full_name = ""  # Cookbook full_name in Spicerack terms
        self.items: Dict[str, BaseItem] = {}
        self._status: str

    @abstractmethod
    def run(self) -> Optional[int]:
        """Excecute the item."""

    @property
    def status(self) -> str:
        """Return the current status.

        Returns:
            str: the string representation of the execution status.

        """
        return self._status

    @property
    def verbose_title(self) -> str:
        """Getter for the verbose_title property, uses the module name if there is no title.

        Returns:
            str: the verbose title of the item.

        """
        if self.title != self.fallback_title:
            return self.title

        return self.name

    @property
    @abstractmethod
    def title(self) -> str:
        """Calculate the title of the instance item.

        Returns:
            str: the title of the item.

        """

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
        empty_sep = "    "
        cont_sep = "|   "

        if is_final:
            base_sep = "`-- "
        else:
            base_sep = "|-- "

        if level == 0:
            return base_sep

        levels = []
        for cont_level in cont_levels:
            if cont_level:
                levels.append(cont_sep)
            else:
                levels.append(empty_sep)

        return "".join(levels) + base_sep


class CookbookItem(BaseItem):
    """Cookbook item class."""

    fallback_title: str = "UNKNOWN (unable to detect title)"
    statuses: Tuple[str, str, str, str] = (
        "NOTRUN",
        "PASS",
        "FAIL",
        "ERROR",
    )  # Status labels
    not_run, success, failed, error = statuses  # Valid statuses variables

    def __init__(
        self,
        class_obj: Type[cookbook.CookbookBase],
        args: Sequence[str],
        spicerack: Spicerack,
    ) -> None:
        """Override parent constructor to add cookbook-specific initialization.

        Arguments:
            class_obj (type): a class derived from :py:class:`spicerack.cookbook.CookbookBase`.
            args (list): any sequence with the command line arguments to pass to the item.
            spicerack (spicerack.Spicerack): the initialized instance of the library.

        """
        super().__init__(args, spicerack)
        if not issubclass(class_obj, cookbook.CookbookBase):
            raise MenuError(f"Class {class_obj} is not a subclass of CookbookBase")

        self._status = CookbookItem.not_run
        self.name = class_obj.spicerack_name
        self.path = class_obj.spicerack_path
        if self.path:
            self.full_name = ".".join([self.path, self.name])
        else:
            self.full_name = self.name

        self.instance = class_obj(spicerack)

    @property
    def title(self) -> str:
        """Calculate the title of the instance item.

        Returns:
            str: the title of the item.

        """
        return self.instance.title

    def run(self) -> int:  # noqa: MC0001
        """Run the cookbook.

        Returns:
            int: the return code to use for this cookbook, it should be zero on success, a positive integer smaller than
            ``128`` and not in the range ``90-99`` (see :ref:`Reserved exit codes<reserved-codes>`) in case of failure.

        """
        ret, args = self._parse_args()
        if ret >= 0:
            return ret

        try:
            runner = self.instance.get_runner(args)
        except BaseException:  # pylint: disable=broad-except
            logger.exception("Exception raised while initializing the Cookbook %s:", self.full_name)
            return cookbook.CLASS_FAIL_INIT_RETCODE

        try:
            description = runner.runtime_description
        except BaseException:  # pylint: disable=broad-except
            logger.exception("Failed to get runtime_description from Cookbook %s:", self.full_name)
            description = ""

        _log.log_task_start(" ".join(("Cookbook", self.full_name, description)).strip())
        message = "raised while executing cookbook"

        try:
            raw_ret = runner.run()
            if raw_ret is None:
                ret = 0
            else:
                ret = raw_ret
        except KeyboardInterrupt:
            logger.error("Ctrl+c pressed")
            self._status = CookbookItem.error
            ret = cookbook.INTERRUPTED_RETCODE
        except SystemExit as e:
            if isinstance(e.code, int):
                ret = e.code
                if e.code == 0:
                    logger.info(
                        "SystemExit(0) %s %s, assuming success:",
                        message,
                        self.full_name,
                    )
                    self._status = CookbookItem.success
                else:
                    logger.exception("SystemExit(%d) %s %s:", e.code, message, self.full_name)
                    self._status = CookbookItem.error
            else:
                logger.exception("SystemExit('%s') %s %s:", e.code, message, self.full_name)
                self._status = CookbookItem.error
                ret = cookbook.EXCEPTION_RETCODE
        except BaseException:  # pylint: disable=broad-except
            logger.exception("Exception %s %s:", message, self.full_name)
            self._status = CookbookItem.failed
            ret = cookbook.EXCEPTION_RETCODE
        else:
            self._status = CookbookItem.success if ret == 0 else CookbookItem.failed

        if ret != 0:
            try:
                runner.rollback()
            except BaseException:  # pylint: disable=broad-except
                logger.exception("Exception %s %s rollback() (exit_code=%d):", message, self.full_name, ret)
                ret = cookbook.ROLLBACK_FAIL_RETCODE

        _log.log_task_end(
            self.status,
            f"Cookbook {self.full_name} (exit_code={ret}) {description}".strip(),
        )

        return ret

    def _parse_args(self) -> Tuple[int, argparse.Namespace]:
        """Get the argument parser from the cookbook and parse the arguments.

        Returns:
            tuple: (int, argparse.Namespace) with the return code to use and the parsed arguments. If the return code is
            different from -1 it means that the cookbook should not be executed either because the help message was
            requested or the parse of the arguments failed or arguments were passed but the cookbook doesn't accept
            arguments.

        """
        args = argparse.Namespace()
        ret, parser = self._safe_call(
            self.instance.argument_parser,
            [],
            {},
            "raised while getting argument parser for cookbook",
            cookbook.GET_ARGS_PARSER_FAIL_RETCODE,
        )

        if ret >= 0 or parser is None:
            return ret, args

        return self._safe_call(
            parser.parse_args,
            [self.args],
            {},
            "raised while parsing arguments for cookbook",
            cookbook.PARSE_ARGS_FAIL_RETCODE,
        )

    def _safe_call(self, func: Callable, args: List, kwargs: Dict, message: str, err_code: int) -> Tuple[int, Any]:
        """Run any callable explicitly catching all exceptions including SystemExit, parsing the code of the latter.

        Arguments:
            func (callable): the callable to call.
            args (list): positional arguments list to pass to the callable.
            kwargs (dict): keyword arguments dictionary to pass to the callable.
            message (str): the message to log in case of exception.
            err_code (int): the error code to return in case of failure.

        Returns:
            tuple: a 2-element tuple with an integer for the return code as the first item and what the callable
            returned in the second item.

        """
        ret_code = -1
        ret_value = None
        try:
            ret_value = func(*args, **kwargs)
        except SystemExit as e:
            if isinstance(e.code, int):
                ret_code = e.code
            else:
                logger.exception("SystemExit('%s') %s %s:", e.code, message, self.full_name)
                ret_code = err_code
        except BaseException:  # pylint: disable=broad-except
            logger.exception("Exception %s %s:", message, self.full_name)
            ret_code = err_code

        return ret_code, ret_value


class TreeItem(BaseItem):
    """Tree of cookbook items class."""

    back_answer: str = "b"
    """str: interactive menu answer to go back to the parent menu."""
    help_answer: str = "h"
    """str: interactive menu answer to print the generic TreeItem help message."""
    quit_answer: str = "q"
    """str: answer to quit the interactive menu."""
    help_message: str = HELP_MESSAGE.format(statuses=CookbookItem.statuses)
    """str: the generic TreeItem help message."""

    def __init__(
        self,
        module: _module_api.CookbooksModuleInterface,
        args: Sequence[str],
        spicerack: Spicerack,
        menu_title: str,
    ) -> None:
        """Override parent constructor to add menu-specific initialization.

        Arguments:
            module (spicerack._module_api.CookbooksModuleInterface): a cookbook Python module.
            args (list): any sequence with the command line arguments to pass to the item.
            spicerack (spicerack.Spicerack): the initialized instance of the library.
            menu_title (str): the title to use for the menu.

        """
        super().__init__(args, spicerack)
        self.module = module
        self.parent: Optional[TreeItem] = None
        self.menu_title = menu_title

        if "." in self.module.__name__:
            self.full_name = self.module.__name__.split(".", 1)[1]
        else:
            self.full_name = self.module.__name__

        if "." in self.full_name:
            self.path, self.name = self.full_name.rsplit(".", 1)
        else:
            self.name = self.full_name

    @property
    def status(self) -> str:
        """Getter for the menu status, returns a string representation of the status of its tasks.

        Returns:
            str: the menu status message.

        """
        completed, total = self.calculate_status()
        if completed == total:
            message = "DONE"
        else:
            message = f"{completed}/{total}"

        return message

    def append(self, item: BaseItem, add_parent: bool = True) -> None:
        """Append an item to this menu.

        Arguments:
            item (spicerack._menu.BaseItem): the item to append.
            add_parent (bool, optional): wheter to set the parent of the new item to the current instance.

        """
        if add_parent and isinstance(item, TreeItem):
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
            print(f"[{item.status}] {name}: {item.title}")

        if self.parent is None:
            print(f"{TreeItem.quit_answer} - Quit")
        else:
            print(f"{TreeItem.back_answer} - Back to parent menu")

        print(f"{TreeItem.help_answer} - Help")

    def calculate_status(self) -> Tuple[int, int]:
        """Calculate the status of a menu, checking the status of all it's tasks recursively.

        Returns:
            tuple: (int, int) with the number of completed and total items.

        """
        completed: int = 0
        total: int = 0
        for item in self.items.values():
            if isinstance(item, TreeItem):
                sub_completed, sub_total = item.calculate_status()
                completed += sub_completed
                total += sub_total
            elif isinstance(item, CookbookItem):
                total += 1
                if item.status != CookbookItem.not_run:
                    completed += 1
            else:  # pragma: no cover | This should never happen
                raise MenuError(f"Unknown item of type {type(item)}")

        return completed, total

    def get_tree(self) -> str:
        """Return the tree representation of the menu as string.

        Returns:
            str: the tree representation of all the collected items.

        """
        lines = self.get_menu_tree(0, [])
        if not lines:
            return ""

        lines_str = "\n".join(lines)
        return f"{self.menu_title}\n{lines_str}\n"

    def get_menu_tree(self, level: int, cont_levels: List[bool]) -> List[str]:
        """Calculate the tree lines for a given menu.

        Arguments:
            level (int): how many levels the item is nested in the tree.
            cont_levels (list): a list of size levels with booleans that indicate for each level if the
                continuation prefix (True) or an empty prefix (False) should be used.

        Returns:
            list: the list of lines that represent the tree.

        """
        lines: List[str] = []
        for i, key in enumerate(sorted(self.items.keys(), key=lambda x: self.items[x].full_name)):
            is_final = i == len(self.items) - 1
            item = self.items[key]
            if isinstance(item, TreeItem) and not item.items:
                continue

            prefix = self._get_line_prefix(level, cont_levels, is_final)
            if self.spicerack.verbose:
                line = f"{prefix}{item.full_name}: {item.title}"
            else:
                line = f"{prefix}{item.full_name}"

            lines.append(line)

            if item.items:
                lines += cast(TreeItem, item).get_menu_tree(level + 1, cont_levels + [not is_final])

        return lines

    def run_once(self) -> None:
        """Run the menu in an interactive way.

        Returns:
            spicerack._menu.TreeItem: the current menu instance.

        """
        print(f"#--- {self.verbose_title} args={self.args} ---#")
        self.show()

        if not sys.stdout.isatty():
            print("Not a tty, exiting.")
            raise StopIteration

        try:
            answer = input(">>> ")
        except (EOFError, KeyboardInterrupt) as e:
            print("QUIT")
            raise StopIteration from e  # Ctrl+d or Ctrl+c pressed while waiting for input

        if not answer:
            return

        if answer == TreeItem.help_answer:
            print(self.help_message)
            return

        if answer == TreeItem.quit_answer and self.parent is None:
            raise StopIteration

        if answer == TreeItem.back_answer and self.parent is not None:
            raise StopIteration

        name, *args = shlex.split(answer)
        if name not in self.items:
            print("==> Invalid input <==")
            return

        item = self.items[name]
        item.args = self._get_item_args(item, args)
        item.run()

    def _get_item_args(self, item: BaseItem, args: Sequence[str]) -> Sequence[str]:
        """Get the arguments to pass to the given item.

        Arguments:
            item (spicerack._menu.BaseItem): the item to pass the arguments to.
            args (list): any sequence with the arguments passed via interactive menu to this item.

        Returns:
            list: the arguments to pass to the item.

        """
        if args:  # Override the item arguments with the ones passed interactively, if any.
            return args

        if self.args:  # Override the item arguments with the ones of the menu, if any.
            return self.args

        return item.args

    @property
    def title(self) -> str:
        """Calculate the title of the instance item.

        Returns:
            str: the title of the item.

        """
        try:
            title = self.module.__title__.splitlines()[0]
        except AttributeError as e:
            logger.debug("Unable to detect title for module %s: %s", self.path, e)
            title = self.fallback_title

        return title
