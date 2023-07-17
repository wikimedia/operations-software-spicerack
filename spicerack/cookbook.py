"""Cookbook module."""
import argparse
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Optional

from spicerack import Spicerack

ROLLBACK_FAIL_RETCODE: int = 93
"""Reserved exit code: the cookbook had failed and raised an exception while executing the rollback() method."""
CLASS_FAIL_INIT_RETCODE: int = 94
"""Reserved exit code: failed to initialize the cookbook."""
GET_ARGS_PARSER_FAIL_RETCODE: int = 95
"""Reserved exit code: the call to get the argument parser failed."""
PARSE_ARGS_FAIL_RETCODE: int = 96
"""Reserved exit code: a cookbook failed to parse arguments."""
INTERRUPTED_RETCODE: int = 97
"""Reserved exit code: a cookbook execution was interrupted."""
NOT_FOUND_RETCODE: int = 98
"""Reserved exit code: no cookbook was found for the selection."""
EXCEPTION_RETCODE: int = 99
"""Reserved exit code: a cookbook raised an exception while executing."""


class ArgparseFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Custom argparse formatter class for cookbooks.

    It can be used as the ``formatter_class`` for the ``ArgumentParser`` instances and it has the capabilities of
    both :py:class:`argparse.ArgumentDefaultsHelpFormatter` and :py:class:`argparse.RawDescriptionHelpFormatter`.
    """


@dataclass(frozen=True)
class LockArgs:
    """A dataclass to represent the arguments to use for the cookbook automatically acquired lock for each run.

    To be used when a cookbook overrides the ``lock_args`` property.

    Arguments:
        suffix: a custom suffix to add to the lock key. The lock key is based on the cookbook's full name and the
            suffix is added to it with a colon separator, for example with suffix ``ro`` the key will become
            ``sre.some.cookbook:ro``.
        concurrency: how many parallel runs of the cookbook with the same lock arguments can be run.
        ttl: the lock time to live (TTL) in seconds. It should be higher than the expected run time of the cookbook.

    """

    suffix: str
    concurrency: int
    ttl: int


class CookbookBase(metaclass=ABCMeta):
    """Base Cookbook class that all cookbooks must extend to use the class-based API to define a cookbook.

    The class will be instantiated without any parameter.
    """

    spicerack_path: str
    """Reserved class property used by Spicerack internally to track the Cookbook's path."""
    spicerack_name: str
    """Reserved class property used by Spicerack internally to track the Cookbook's name."""

    def __init__(self, spicerack: Spicerack):
        """Initialize the instance and store the Spicerack instance into ``self.spicerack``.

        Arguments:
            spicerack: the Spicerack accessor instance with which the cookbook can access all the Spicerack
                capabilities.

        """
        self.spicerack = spicerack

    @property
    def title(self) -> str:
        """Returns the title of the Cookbook, must be a single line string.

        The default implementation returns the first line of the class docstring if there is any, a single
        dash otherwise.
        """
        if self.__doc__ is None:
            return "-"

        return self.__doc__.splitlines()[0]

    def argument_parser(self) -> argparse.ArgumentParser:
        """Optionally define an argument parser for the cookbook, if the cookbook accepts CLI arguments.

        The default implementation returns an empty ``ArgumentParser`` instance that doesn't accept any arguments and
        uses the class docstring as description. The arguments will be parsed by the Spicerack framework.
        """
        return argparse.ArgumentParser(description=self.__doc__, formatter_class=ArgparseFormatter)

    @abstractmethod
    def get_runner(self, args: argparse.Namespace) -> "CookbookRunnerBase":
        """Return the runner object that will be used to execute the cookbook.

        Derived classes must override this method and can perform any initialization and validation of the parsed
        arguments, but must not perform any real action here.

        If any exception is raised in this method Spicerack will not execute the cookbook.

        Arguments:
            args: the parsed arguments that were parsed using the defined ``argument_parser()``.

        Raises:
            BaseException: any exception raised in the ``get_runner()`` method will be catched by Spicerack and the
                Cookbook will not be executed.

        Returns:
            Must return an instance of a custom class derived from :py:class:`spicerack.cookbook.CookbookRunnerBase`
            that implements the actual execution of the cookbook.

        """


class CookbookRunnerBase(metaclass=ABCMeta):
    """Base class that all cookbooks must extend to use the class-based API to define the execution plan.

    The constructor of the class is left outside of the interface contract so that each cookbook is free to customize
    it as needed.
    """

    max_concurrency: int = 20
    """How many parallel runs of a specific cookbook inheriting from this class are accepted. If the ``lock_args``
    property is defined this one is ignored."""
    lock_ttl: int = 1800
    """The concurrency lock time to live (TTL) in seconds. For each concurrent run a lock is acquired for this amount
    of seconds. If the ``lock_args`` property is defined this one is ignored."""

    @property
    def runtime_description(self) -> str:
        """Optional message to be used as the runtime description of the cookbook.

        Cookbooks can override this instance property to define their custom description, also based on the given
        command line arguments. For example this will be used in the task start/end messages. The default
        implementation returns an empty string.
        """
        return ""

    @property
    def lock_args(self) -> LockArgs:
        """Optional property to dynamically modify the arguments used for the distributed lock of the cookbook runs.

        It is useful to allow to set a different concurrency and TTL for the cookbook's lock  based on the operation
        performed. For example allowing for an increased concurrency when performing read-only operations, or to
        differentiate the lock based on the given arguments, say having different locks for different datacenters or
        clusters.
        This property by default returns the static ``max_concurrency`` and ``lock_ttl`` class properties with an
        empty suffix.

        Returns:
            the arguments to be used by Spicerack to acquire the lock for the current cookbook.

        """
        return LockArgs(suffix="", concurrency=self.max_concurrency, ttl=self.lock_ttl)

    @abstractmethod
    def run(self) -> Optional[int]:
        """Execute the cookbook.

        Returns:
            The return code of the cookbook, it should be zero or :py:data:`None` on success, a positive
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
        For example it can be used to cleanup any left-over inconsistent state as if the cookbook was never run.

        Any un-caught exception raised by this method will be caught by Spicerack and logged, along with the original
        exit code of the cookbook. The final exit code will be the reserved
        :py:const:`cookbooks.ROLLBACK_FAIL_RETCODE`.
        """
