"""Cookbook internal module."""
import argparse
import importlib
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple, Type, cast

from wmflib.config import load_yaml_config

from spicerack import Spicerack, _log, _module_api, cookbook
from spicerack._menu import BaseItem, CookbookItem, MenuError, TreeItem
from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class CookbookError(SpicerackError):
    """Custom exception class for errors of this module."""


class CookbookCollection:
    """Collect and represent available cookbooks."""

    cookbooks_module_prefix: str = "cookbooks"

    def __init__(
        self,
        base_dir: str,
        args: List[str],
        spicerack: Spicerack,
        path_filter: str = "",
    ) -> None:
        """Initialize the class and collect all the cookbook menu items.

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
        self.path_filter = path_filter

        module = import_module(self.cookbooks_module_prefix)
        self.menu = TreeItem(module, self.args, self.spicerack, self.cookbooks_module_prefix)
        self._collect()

    def get_item(self, path: str) -> Optional[BaseItem]:
        """Retrieve the item for a given path.

        Arguments:
            path (str): the path of the item to look for.

        Returns:
            None: when no item is found.
            spicerack._menu.TreeItem: when the item found is a menu of cookbooks.
            spicerack._menu.CookbookItem: when the item found is a single cookbook.

        """
        item: Optional[BaseItem] = None
        parts = path.split(".")
        multiple_class_name = ".".join(parts[-2:])
        for i, subpath in enumerate(parts):
            if i == 0:  # Initial menu
                item = self.menu
            elif item is not None and subpath in item.items.keys():  # Submenu or child cookbook found
                item = item.items[subpath]
            elif item is not None and i == len(parts) - 2 and multiple_class_name in item.items.keys():
                # Found cookbook in a module that has multiple class API cookbooks
                item = item.items[multiple_class_name]
                break
            else:
                item = None

        return item

    def _create_menu_for_path(self, path: str) -> TreeItem:
        """Create the menu for a given path, including intermediate levels, if missing. Return the existing one if any.

        Arguments:
            path (str): the path of the item to look for.

        Returns:
            spicerack._menu.TreeItem: the existing or created menu.

        """
        item: TreeItem = self.menu
        if path == self.cookbooks_module_prefix:
            return item

        progressive_path = [self.cookbooks_module_prefix]
        for subpath in path.split(".")[1:]:
            progressive_path.append(subpath)
            if subpath in item.items:
                item = cast(TreeItem, item.items[subpath])
            else:
                module_name = ".".join(progressive_path)
                submenu = TreeItem(
                    import_module(module_name),
                    self.args,
                    self.spicerack,
                    self.cookbooks_module_prefix,
                )
                # When collecting the cookbooks and creating the TreeItem instances, the relation to the parent
                # menu should be skipped for those intermediate menus created for coherence but that should not be
                # accessible by the user, like when using a path_filter.
                add_parent = submenu.full_name.startswith(self.path_filter) and submenu.full_name != self.path_filter
                item.append(submenu, add_parent=add_parent)
                item = submenu

        return item

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
            dirnames.remove("__pycache__")
        except ValueError:
            pass

        for filename in filenames.copy():  # TODO: add support for cookbooks in __init__.py files
            if filename == "__init__.py" or not filename.endswith(".py"):
                filenames.remove(filename)

        return dirnames, filenames

    def _collect(self) -> None:
        """Collect available cookbooks starting from a base path."""
        for dirpath, dirnames, filenames in os.walk(self.base_dir):
            dirnames, filenames = CookbookCollection._filter_dirnames_and_filenames(dirnames, filenames)
            if not filenames and not dirnames:
                continue

            # Sort the directories and files to be recursed in-place, required by os.walk().
            dirnames.sort()
            filenames.sort()

            relpath = os.path.relpath(dirpath, start=self.base_dir)
            if relpath == ".":
                prefix = ""
                module_prefix = self.cookbooks_module_prefix
            else:
                prefix = relpath.replace("/", ".").rstrip(".")
                module_prefix = ".".join([self.cookbooks_module_prefix, prefix])

            if self._should_filter(prefix):
                continue

            try:
                menu = self._create_menu_for_path(module_prefix)
            except CookbookError as e:
                logger.error(e)
                continue

            for filename in filenames:
                module_name = ".".join((module_prefix, os.path.splitext(filename)[0]))
                self._collect_filename(module_name, menu)

    def _collect_filename(self, module_name: str, menu: TreeItem) -> None:
        """Collect all the available cookbooks in the given module and add them to the menu.

        Arguments:
            module_name (str): the Python module to load.
            menu (spicerack._menu.TreeItem): the menu to append the collected cookbook to.

        """
        try:
            classes = self._collect_module_cookbooks(import_module(module_name))
        except CookbookError as e:
            logger.error(e)
            return

        for class_obj in classes:
            try:
                cookbook_item = CookbookItem(class_obj, self.args, self.spicerack)
            except MenuError as e:
                logger.error(e)
                continue

            if self._should_filter(cookbook_item.full_name):
                continue

            menu.append(cookbook_item)

    def _should_filter(self, name: str) -> bool:
        """Check if a given path or full name should be skipped because not matching the current filter.

        Arguments:
            name (str): the name to check, can be either a CookbookItem full name or a TreeItem path.

        Returns:
            bool: :py:data:`True` if the item should be skipped, :py:data:`False` otherwise.

        """
        if not self.path_filter:
            return False

        if name.startswith(self.path_filter[: len(name)]):
            return False

        return True

    def _collect_module_cookbooks(
        self, module: _module_api.CookbooksModuleInterface
    ) -> List[Type[cookbook.CookbookBase]]:
        """Collect all classes derived from CookbookBase in the given module.

        Arguments:
            module (spicerack._module_api.CookbooksModuleInterface): the module to check for cookbook classes.

        Returns:
            list: a list of CookbookBase derived class objects.

        """
        attrs = [getattr(module, attr) for attr in dir(module)]
        classes = [
            attr
            for attr in attrs
            if isinstance(attr, type) and issubclass(attr, cookbook.CookbookBase) and attr.__module__ == module.__name__
        ]

        if not classes:  # No class API cookbook found, convert a module API cookbook into a class
            classes.append(self._convert_module_in_cookbook(module))
        elif len(classes) == 1:  # Avoid the unnecessary further nested namespace
            class_obj = classes[0]
            full_name = class_obj.__module__.split(".", 1)[1]
            if "." in full_name:
                class_obj.spicerack_path, class_obj.spicerack_name = full_name.rsplit(".", 1)
            else:
                class_obj.spicerack_path = ""
                class_obj.spicerack_name = full_name
        else:  # Inject the class module name as part of the class name and set the module as that of the parent
            for class_obj in classes:
                full_name_prefix = class_obj.__module__.split(".", 1)[1]
                if "." in full_name_prefix:
                    class_obj.spicerack_path, name_prefix = full_name_prefix.rsplit(".", 1)
                    class_obj.spicerack_name = ".".join([name_prefix, class_obj.__name__])
                else:
                    class_obj.spicerack_path = ""
                    class_obj.spicerack_name = ".".join([full_name_prefix, class_obj.__name__])

        return classes

    def _convert_module_in_cookbook(self, module: _module_api.CookbooksModuleInterface) -> Type[cookbook.CookbookBase]:
        """Convert a module API based cookbook into a class API cookbook.

        Arguments:
            module (spicerack._module_api.CookbooksModuleInterface): the module to convert.

        Returns:
            type: a dynamically generated class derived from :py:class:`spicerack.cookbook.CookbookBase`.

        """
        module_name, name = module.__name__.rsplit(".", 1)
        try:
            title = module.__title__.splitlines()[0]  # Force it to be one-line only
        except AttributeError as e:
            logger.debug("Unable to detect title for module %s: %s", module.__name__, e)
            title = CookbookItem.fallback_title

        try:
            run = module.run
        except AttributeError as e:
            raise CookbookError(f"Unable to find run function in module {module.__name__}") from e

        runner_name = f"{name}Runner"
        runner = type(
            runner_name,
            (_module_api.CookbookModuleRunnerBase,),
            {"_run": staticmethod(run)},
        )
        runner.__module__ = module_name

        attributes = {
            "__module__": module_name,
            "__name__": name,
            "spicerack_name": name,
            "spicerack_path": module_name.split(".", 1)[1] if "." in module_name else "",
            "title": title,
            "get_runner": lambda _, args: runner(args, self.spicerack),
        }

        try:
            args_parser = module.argument_parser
            attributes["argument_parser"] = lambda _: args_parser()
        except AttributeError:
            # The cookbook doesn't accept any argument, set a default empty parser
            attributes["argument_parser"] = lambda _: argparse.ArgumentParser(
                description=module.__doc__, formatter_class=cookbook.ArgparseFormatter
            )

        cookbook_class = type(name, (cookbook.CookbookBase,), attributes)
        return cookbook_class


def argument_parser() -> argparse.ArgumentParser:
    """Get the CLI argument parser.

    If the COOKBOOK is passed as a path, it will be converted to a Python module syntax.

    Returns:
        argparse.ArgumentParser: the argument parser instance.

    """
    parser = argparse.ArgumentParser(description="Spicerack Cookbook Runner")
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help=(
            "List all available cookbooks, if -v/--verbose is set print also their description. If a COOKBOOK is "
            "also specified, it will be used as a prefix filter."
        ),
    )
    parser.add_argument(
        "-c",
        "--config-file",
        default="/etc/spicerack/config.yaml",
        help="Path to the Spicerack configuration file to load.",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Set the DRY-RUN mode, also for the cookbook.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output, also for the cookbook.",
    )
    parser.add_argument(
        "cookbook",
        metavar="COOKBOOK",
        nargs="?",
        type=cookbook_path_type,
        default="",
        help=(
            "Either a relative path of the Python file to execute (group/cookbook.py) or the name of the Python "
            "module to execute (group.cookbook). If the selected path/module is a directory or is not set, an "
            "interactive menu will be shown."
        ),
    )
    parser.add_argument(
        "cookbook_args",
        metavar="COOKBOOK_ARGS",
        nargs=argparse.REMAINDER,
        help="Collect all the remaining arguments to be passed to the cookbook or menu to execute.",
    )

    return parser


def cookbook_path_type(path: str) -> str:
    """Convert a COOKBOOK path to module syntax, if it's in path syntax.

    Arguments:
        path (str): the path to be converted.

    Returns:
        str: the converted path in module syntax.

    """
    cookbook_path, ext = os.path.splitext(path)
    if ext == ".py":
        path = cookbook_path.replace("/", ".")

    return path


def import_module(module_name: str) -> _module_api.CookbooksModuleInterface:
    """Import a Python module.

    Arguments:
        module_name (str): the name of the module to load.

    Returns:
        list: a list of :py:class:`spicerack.cookbook.CookbookBase` objects, one for each collected cookbook. In case
        of module API cookbooks it converts them automatically to a class API one.

    Raises:
        spicerack._cookbook.CookbookError: on failure to load the module.

    """
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        raise CookbookError(f"Failed to import module {module_name}: {e}") from e

    return cast(_module_api.CookbooksModuleInterface, module)


def execute_cookbook(config: Dict[str, str], args: argparse.Namespace, cookbooks: CookbookCollection) -> Optional[int]:
    """Execute a single cookbook with its arguments.

    Arguments:
        config (dict): the configuration dictionary.
        args (argparse.Namespace): the parsed arguments.
        cookbooks (spicerack._cookbook.CookbookCollection): the collected cookbooks.

    Returns:
        int: the return code, 0 on success, non-zero on cookbook failure, 98 on cookbook exception.

    """
    if args.cookbook:
        path = ".".join((CookbookCollection.cookbooks_module_prefix, args.cookbook))
    else:
        path = CookbookCollection.cookbooks_module_prefix

    cookbook_item = cookbooks.get_item(path)
    if cookbook_item is None:
        logger.error("Unable to find cookbook %s", args.cookbook)
        return cookbook.NOT_FOUND_RETCODE

    base_path = os.path.join(config["logs_base_dir"], cookbook_item.path.replace(".", os.sep))
    _log.setup_logging(
        base_path,
        cookbook_item.name,
        cookbooks.spicerack.username,
        dry_run=args.dry_run,
        host=config.get("tcpircbot_host", None),
        port=int(config.get("tcpircbot_port", 0)),
    )

    logger.debug("Executing cookbook with args: %s", args)
    return cookbook_item.run()


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    """Entry point, run the tool.

    Arguments:
        argv (list, optional): the list of command line arguments to parse.

    Returns:
        int: the return code, zero on success, non-zero on failure.

    """
    args = argument_parser().parse_args(argv)
    config = load_yaml_config(args.config_file)
    cookbooks_base_dir = os.path.expanduser(config["cookbooks_base_dir"])
    sys.path.append(cookbooks_base_dir)
    params = config.get("instance_params", {})
    params.update({"verbose": args.verbose, "dry_run": args.dry_run})

    try:
        spicerack = Spicerack(**params)
    except TypeError as e:
        print(
            "Unable to instantiate Spicerack, check your configuration:",
            e,
            file=sys.stderr,
        )
        return 1

    cookbooks = CookbookCollection(cookbooks_base_dir, args.cookbook_args, spicerack, path_filter=args.cookbook)

    if args.list:
        print(cookbooks.menu.get_tree(), end="")
        return 0

    return execute_cookbook(config, args, cookbooks)
