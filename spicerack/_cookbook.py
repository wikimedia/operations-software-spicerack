"""Cookbook internal module."""

import argparse
import importlib
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Optional, cast

from wmflib.config import load_yaml_config

from spicerack import Spicerack, SpicerackExtenderBase, _log, _module_api, cookbook
from spicerack._menu import BaseItem, CookbookItem, MenuError, TreeItem, get_module_title
from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class CookbookError(SpicerackError):
    """Custom exception class for errors of this module."""


class CookbookCollection:
    """Collect and represent available cookbooks."""

    cookbooks_module_prefix: str = "cookbooks"

    def __init__(
        self,
        *,
        base_dirs: list[Path],
        args: Sequence[str],
        spicerack: Spicerack,
        path_filter: str = "",
    ) -> None:
        """Initialize the class and collect all the cookbook menu items.

        Arguments:
            base_dirs: the list of base directories from where to start looking for cookbooks.
            args: the list of arguments to pass to the collected items.
            spicerack: the initialized instance of the library.
            path_filter: an optional relative module path to filter for. If set, only cookbooks that are part of this
                subtree will be collected.

        """
        self.base_dirs = [base_dir / self.cookbooks_module_prefix for base_dir in base_dirs]
        self.args = args
        self.spicerack = spicerack
        self.path_filter = path_filter

        module = import_module(self.cookbooks_module_prefix)
        self.menu = TreeItem(module, self.args, self.spicerack, self.cookbooks_module_prefix)
        for base_dir in self.base_dirs:
            self._collect(base_dir)

    def get_item(self, path: str) -> Optional[BaseItem]:
        """Retrieve the item for a given path.

        Arguments:
            path: the path of the item to look for.

        Returns:
            None: when no item is found.
            spicerack._menu.TreeItem: when the item found is a menu of cookbooks.
            spicerack._menu.CookbookItem: when the item found is a single cookbook.

        """
        if path:
            effective_path = ".".join((self.cookbooks_module_prefix, path))
        else:
            effective_path = self.cookbooks_module_prefix

        item: Optional[BaseItem] = None
        parts = effective_path.split(".")
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
            path: the path of the item to look for.

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
                # Use the parent owner_team if set
                default_owner = cookbook.CookbookBase.owner_team
                if item.owner_team != default_owner and submenu.owner_team == default_owner:
                    submenu.module.__owner_team__ = item.owner_team

                # When collecting the cookbooks and creating the TreeItem instances, the relation to the parent
                # menu should be skipped for those intermediate menus created for coherence but that should not be
                # accessible by the user, like when using a path_filter.
                add_parent = submenu.full_name.startswith(self.path_filter) and submenu.full_name != self.path_filter
                item.append(submenu, add_parent=add_parent)
                item = submenu

        return item

    def _collect(self, base_dir: Path) -> None:
        """Collect available cookbooks starting from a base path.

        Arguments:
            base_dir: the directory where to start collecting the cookbooks.

        """
        for dirpath in base_dir.rglob(""):  # Selects only directories
            if dirpath.name == "__pycache__":
                continue

            relpath = dirpath.relative_to(base_dir)
            if relpath.name:
                prefix = str(relpath).replace("/", ".").rstrip(".")
                module_prefix = f"{self.cookbooks_module_prefix}.{prefix}"
            else:
                prefix = ""
                module_prefix = self.cookbooks_module_prefix

            if self._should_filter(prefix):
                continue

            try:
                menu = self._create_menu_for_path(module_prefix)
            except CookbookError as e:
                logger.error(e)
                continue

            for filepath in dirpath.glob("[!_]*.py"):  # Excludes files starting with an underscore, like __init__.py
                module_name = f"{module_prefix}.{filepath.stem}"
                self._collect_filename(module_name, menu)

    def _collect_filename(self, module_name: str, menu: TreeItem) -> None:
        """Collect all the available cookbooks in the given module and add them to the menu.

        Arguments:
            module_name: the Python module to load.
            menu: the menu to append the collected cookbook to.

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

            # Use the parent owner_team if set
            default_owner = cookbook.CookbookBase.owner_team
            if menu.owner_team != default_owner and cookbook_item.owner_team == default_owner:
                cookbook_item.instance.owner_team = menu.owner_team

            if self._should_filter(cookbook_item.full_name):
                continue

            menu.append(cookbook_item)

    def _should_filter(self, name: str) -> bool:
        """Check if a given path or full name should be skipped because not matching the current filter.

        Arguments:
            name: the name to check, can be either a CookbookItem full name or a TreeItem path.

        Returns:
            :py:data:`True` if the item should be skipped, :py:data:`False` otherwise.

        """
        if not self.path_filter:
            return False

        if name.startswith(self.path_filter[: len(name)]):
            return False

        return True

    def _collect_module_cookbooks(
        self, module: _module_api.CookbooksModuleInterface
    ) -> list[type[cookbook.CookbookBase]]:
        """Collect all classes derived from CookbookBase in the given module.

        Arguments:
            module: the module to check for cookbook classes.

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

    def _convert_module_in_cookbook(  # noqa: MC0001
        self, module: _module_api.CookbooksModuleInterface
    ) -> type[cookbook.CookbookBase]:
        """Convert a module API based cookbook into a class API cookbook.

        Arguments:
            module: the module to convert.

        Returns:
            type: a dynamically generated class derived from :py:class:`spicerack.cookbook.CookbookBase`.

        """
        module_name, name = module.__name__.rsplit(".", 1)
        title = get_module_title(module) or CookbookItem.fallback_title

        try:
            owner_team = module.__owner_team__
        except AttributeError:
            owner_team = cookbook.CookbookBase.owner_team

        try:
            run = module.run
        except AttributeError as e:
            raise CookbookError(f"Unable to find run function in module {module.__name__}") from e

        if hasattr(module, "MAX_CONCURRENCY"):
            max_concurrency = module.MAX_CONCURRENCY
        else:
            max_concurrency = cookbook.CookbookRunnerBase.max_concurrency

        if hasattr(module, "LOCK_TTL"):
            lock_ttl = module.LOCK_TTL
        else:
            lock_ttl = cookbook.CookbookRunnerBase.lock_ttl

        runner_name = f"{name}Runner"
        runner = type(
            runner_name,
            (_module_api.CookbookModuleRunnerBase,),
            {
                "_run": staticmethod(run),
                "max_concurrency": max_concurrency,
                "lock_ttl": lock_ttl,
            },
        )
        runner.__module__ = module_name

        attributes = {
            "__module__": module_name,
            "__name__": name,
            "owner_team": owner_team,
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

    """
    parser = argparse.ArgumentParser(
        description="Spicerack Cookbook Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="See also https://wikitech.wikimedia.org/wiki/Spicerack/Cookbooks",
        allow_abbrev=False,  # Prevent matching of cookbook options
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help=(
            "List all available cookbooks and their owner team, if -v/--verbose is set print also their description. "
            "If a COOKBOOK is also specified, it will be used as a prefix filter."
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
        "--no-locks",
        action="store_true",
        help="Do not acquire or check distributed locks on etcd. To be used only if there are issues with etcd.",
    )
    parser.add_argument(
        "cookbook",
        metavar="COOKBOOK",
        nargs="?",
        type=cookbook_path_type,
        default="",
        help=(
            "Either the name of the Python module to execute (sre.hosts.downtime) or the relative path of the Python "
            "file to execute (sre/hosts/downtime.py).  If the selected path/module is a directory (sre.hosts) or is "
            "not set, an interactive menu will be shown. Each directory listed in the `cookbooks_base_dirs` key of the"
            "configuration file represents a checked out cookbook repository containing a `cookbooks` subfolder. All "
            "paths specified must be relative to theses subfolders."
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
        path: the path to be converted.

    """
    if path.endswith(".py"):
        path = path[:-3].replace("/", ".")

    return path


def import_module(module_name: str) -> _module_api.CookbooksModuleInterface:
    """Import a Python module and return it.

    Arguments:
        module_name: the name of the module to load.

    Raises:
        spicerack._cookbook.CookbookError: on failure to load the module.

    """
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        raise CookbookError(f"Failed to import module {module_name}: {e}") from e

    return cast(_module_api.CookbooksModuleInterface, module)


def _import_extender_class(extender_class_param: str) -> SpicerackExtenderBase:
    """Import the extender class, ensure it's a subclass of SpicerackExtenderBase and return it.

    Arguments:
        extender_class_param: the configuration file parameter with the fully qualified class name.

    """
    extender_module_name, extender_class_name = extender_class_param.rsplit(".", 1)
    extender_module = import_module(extender_module_name)
    extender_class = getattr(extender_module, extender_class_name)
    if issubclass(extender_class, SpicerackExtenderBase):
        return extender_class

    raise TypeError(f"Extender class {extender_class_param} is not a subclass of spicerack.SpicerackExtenderBase.")


def get_cookbook_callback(
    cookbooks_base_dirs: list[Path],
) -> Callable[["Spicerack", str, Sequence[str]], Optional["BaseItem"]]:
    """Returns the cookbook callback function needed to load a cookbook from another cookbook."""

    def get_cookbook(spicerack: Spicerack, cookbook_path: str, cookbook_args: Sequence[str] = ()) -> Optional[BaseItem]:
        """Get a cookbook item if it exists.

        Arguments:
            spicerack: the Spicerack class instance.
            cookbook_path: the cookbook name/path.
            cookbook_args: the sequence of CLI arguments to pass to the cookbook.

        Returns:
            :py:data:`None` if there is no cookbook found, the cookbook item otherwise.

        """
        cookbooks = CookbookCollection(
            base_dirs=cookbooks_base_dirs,
            args=cookbook_args,
            spicerack=spicerack,
            path_filter=cookbook_path,
        )
        return cookbooks.get_item(cookbook_path)

    return get_cookbook


def main(argv: Optional[Sequence[str]] = None) -> Optional[int]:  # noqa: MC0001
    """Entry point, run the tool.

    Arguments:
        argv: the list of command line arguments to parse.

    Returns:
        The return code, zero on success, non-zero on failure.

    """
    args = argument_parser().parse_args(argv)
    if not args.cookbook:
        args.cookbook = ""

    config = load_yaml_config(args.config_file)
    cookbooks_base_dirs = []
    for base_dir in config["cookbooks_base_dirs"]:
        base_dir_path = Path(base_dir).expanduser()
        cookbooks_base_dirs.append(base_dir_path)
        sys.path.append(str(base_dir_path))

    if not cookbooks_base_dirs:
        print(
            "No cookbooks paths are specified in the `cookbooks_base_dirs` key of the configuration file.",
            file=sys.stderr,
        )
        return 1

    if config.get("external_modules_dir") is not None:
        sys.path.append(str(Path(config["external_modules_dir"]).expanduser()))

    params = config.get("instance_params", {})
    get_cookbook = get_cookbook_callback(cookbooks_base_dirs)
    params.update({"verbose": args.verbose, "dry_run": args.dry_run, "get_cookbook_callback": get_cookbook})
    if "extender_class" in params:
        try:
            params["extender_class"] = _import_extender_class(params["extender_class"])
        except Exception as e:  # pylint: disable=broad-except
            print(f"Failed to import the extender_class {params['extender_class']}:", e, file=sys.stderr)
            return 1

    if args.no_locks:
        params["etcd_config"] = ""  # Disable locking support

    try:
        spicerack = Spicerack(**params)
    except TypeError as e:
        print("Unable to instantiate Spicerack, check your configuration:", e, file=sys.stderr)
        return 1

    cookbooks = CookbookCollection(
        base_dirs=cookbooks_base_dirs, args=args.cookbook_args, spicerack=spicerack, path_filter=args.cookbook
    )
    if args.list:
        print(cookbooks.menu.get_tree(), end="")
        return 0

    cookbook_item = cookbooks.get_item(args.cookbook)
    if cookbook_item is None:
        logger.error("Unable to find cookbook %s", args.cookbook)
        return cookbook.NOT_FOUND_RETCODE

    base_path = Path(config["logs_base_dir"]).expanduser() / cookbook_item.path.replace(".", os.sep)
    _log.setup_logging(
        base_path,
        cookbook_item.name,
        spicerack.username,
        dry_run=args.dry_run,
        host=config.get("tcpircbot_host", None),
        port=int(config.get("tcpircbot_port", 0)),
        notify_logger_enabled=config.get("user_input_notifications_enabled", False),
    )

    logger.debug("Executing cookbook %s with args: %s", args.cookbook, args.cookbook_args)
    return cookbook_item.run()
