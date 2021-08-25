"""Cookbook module."""
import argparse
from abc import ABCMeta, abstractmethod
from typing import Optional

from spicerack import Spicerack

ROLLBACK_FAIL_RETCODE = 93
"""int: Reserved exit code: the cookbook had failed and raised an exception while executing the rollback() method."""
CLASS_FAIL_INIT_RETCODE = 94
"""int: Reserved exit code: failed to initialize the cookbook."""
GET_ARGS_PARSER_FAIL_RETCODE = 95
"""int: Reserved exit code: the call to get the argument parser failed."""
PARSE_ARGS_FAIL_RETCODE = 96
"""int: Reserved exit code: a cookbook failed to parse arguments."""
INTERRUPTED_RETCODE = 97
"""int: Reserved exit code: a cookbook execution was interrupted."""
NOT_FOUND_RETCODE = 98
"""int: Reserved exit code: no cookbook was found for the selection."""
EXCEPTION_RETCODE = 99
"""int: Reserved exit code: a cookbook raised an exception while executing."""


class ArgparseFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Custom argparse formatter class for cookbooks.

    It can be used as the ``formatter_class`` for the ``ArgumentParser`` instances and it has the capabilities of
    both :py:class:`argparse.ArgumentDefaultsHelpFormatter` and :py:class:`argparse.RawDescriptionHelpFormatter`.
    """


class CookbookBase(metaclass=ABCMeta):
    """Base Cookbook class that all cookbooks must extend to use the class-based API to define a cookbook.

    The class will be instantiated without any parameter.
    """

    spicerack_path: str
    """Reserved class property used by Spicerack internally to track the Cookbook's path."""
    spicerack_name: str
    """Reserved class property used by Spicerack internally to track the Cookbook's name."""

    def __init__(self, spicerack: Spicerack):
        """Initializee the instance and store the Spicerack instance into ``self.spicerack``.

        Arguments:
            spicerack (spicerack.Spicerack): the Spicerack accessor instance with which the cookbook can access all the
                Spicerack capabilities.

        """
        self.spicerack = spicerack

    @property
    def title(self) -> str:
        """Retuns the title of the Cookbook, must be a single line string.

        The default implementation returns the first line of the class docstring if there is any, a single
        dash otherwise.

        Returns:
            str: the cookbook static title.

        """
        if self.__doc__ is None:
            return "-"

        return self.__doc__.splitlines()[0]

    def argument_parser(self) -> argparse.ArgumentParser:
        """Optionally define an argument parser for the cookbook, if the cookbook accepts CLI arguments.

        The default implementation returns an empty ``ArgumentParser`` instance that doesn't accept any arguments and
        uses the class docstring as description.

        Returns:
            argparse.ArgumentParser: the argument parser object, the arguments will be parsed by the framework.

        """
        return argparse.ArgumentParser(description=self.__doc__, formatter_class=ArgparseFormatter)

    @abstractmethod
    def get_runner(self, args: argparse.Namespace) -> "CookbookRunnerBase":
        """Return the runner object that will be used to execute the cookbook.

        Derived classes must override this method and can perform any initialization and validation of the parsed
        arguments, but must not perform any real action here.

        If any exception is raised in this method Spicerack will not execute the cookbook.

        Arguments:
            args (argparse.Namespace): the parsed arguments that were parsed using the defined ``argument_parser()``.

        Raises:
            BaseException: any exception raised in the ``get_runner()`` method will be catched by Spicerack and the
                Cookbook will not be executed.

        Returns:
            spicerack.cookbook.CookbookRunnerBase: an instance of a custom class derived from
            :py:class:`spicerack.cookbook.CookbookRunnerBase` that implements the actual execution of the cookbook.

        """


class CookbookRunnerBase(metaclass=ABCMeta):
    """Base class that all cookbooks must extend to use the class-based API to define the execution plan.

    The constructor of the class is left outside of the interface contract so that each cookbook is free to customize
    it as needed.
    """

    @property
    def runtime_description(self) -> str:
        """Optional message to be used as the runtime description of the cookbook.

        Cookbooks can override this instance property to define their custom description, also based on the given
        command line arguments. For example this will be used in the task start/end messages.

        Returns:
            str: the runtime description. If not overriden an empty string will be used.

        """
        return ""

    @abstractmethod
    def run(self) -> Optional[int]:
        """Excute the cookbook.

        Returns:
            int, None: the return code of the cookbook, it should be zero or :py:data:`None` on success, a positive
            integer smaller than ``128`` and not in the range ``90-99``
            (see :ref:`Reserved exit codes<reserved-codes>`) in case of failure.

        Raises:
            BaseException: any exception raised in the ``run()`` method will be catched by Spicerack and the Cookbook
                execution will be considered failed.

        """

    def rollback(self) -> None:
        """Called by Spicerack when the cookbook fails the execution.

        This method by default does nothing. Cookbooks classes that inherit from this one can override it to add their
        own custom actions to perform on error to rollback to a previous state.
        The method will be called if the cookbook raises any un-caught exception or exits with a non-zero exit code.
        For example it can be used to cleanup any left-over unconsistent state as if the cookbook was never run.

        Any un-caught exception raised by this method will be caught by Spicerack and logged, along with the original
        exit code of the cookbook. The final exit code will be the reserved
        :py:const:`cookbooks.ROLLBACK_FAIL_RETCODE`.
        """
