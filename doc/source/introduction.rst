Introduction
============


.. include:: ../../README.rst


Cookbooks API
-------------

Collection of cookbooks to automate and orchestrate operations in the WMF infrastructure.
The cookbooks will be executed by the ``cookbook`` entry point script of the ``spicerack`` package.

Cookbooks hierarchy
^^^^^^^^^^^^^^^^^^^

The cookbooks must be structured in a tree, as they can be run also from an interactive menu that shows the tree from
an arbitrary entry point downwards.

Each cookbook filename must be a valid Python module name, hence all lowercase, with underscore if that improves
readability and that doesn't start with a number.

Given that the cookbooks are imported dynamically, a broader set of characters like dashes and starting with a number
are technically allowed and the current standard at WMF is to name the cookbooks with dashes instead of underscores.

Example of cookbooks tree::

    cookbooks
    |-- __init__.py
    |-- top-level-cookbook.py
    |-- group1
    |   |-- __init__.py
    |   `-- important-cookbook.py
    `-- group2
        |-- __init__.py
        `-- subgroup1
            |-- __init__.py
            `-- some-task.py

API interfaces
^^^^^^^^^^^^^^

Each cookbook must follow one of the two available API interfaces:

* `Class interface`_ (preferred)
* `Module interface`_

Class interface
"""""""""""""""

When using the class interface, you will need to define two classes:

* one *runner* class that extends :py:class:`spicerack.cookbook.CookbookRunnerBase` and implements the ``__init__``, ``run``
  and (optionally) ``rollback`` and ``runtime_description`` methods
* one *base* class that extends :py:class:`spicerack.cookbook.CookbookBase`  and implements the ``argument_parser`` and
  ``get_runner`` methods.

Let's see how to implement a simple cookbook that depools a service from dns discovery.
Our cookbook will accept three command-line arguments: the service name, the datacenter and the action to perform.
::

    import argparse
    from wmflib.constants import CORE_DATACENTERS
    from spicerack.cookbook import CookbookRunnerBase, CookbookBase
    class ServiceRouter(CookbookBase):
        def argument_parser(self) -> argparse.ArgumentParser:
            parser = super().argument_parser() # returns a bare ArgumentParser with the correct defaults
            parser.add_argument("service")
            parser.add_argument("datacenter", choice=CORE_DATACENTERS)
            parser.add_argument("action", choice=("pool", "depool"))
            return parser

        def get_runner(self, args) -> CookbookRunnerBase:
            return ServiceRouterRunner(args, self.spicerack)

Here, `self.spicerack` is a an initialized :py:class:`spicerack.Spicerack` instance.
Now we need to implement the class that will actually do the work.
There are four methods to implement:

* `__init__(args, spicerack)` to set up the properties of the class
* `runtime_description`, returning a string that will be used to log the cookbook action to SAL
* `run` that should contain the cookbook operations.
* `rollback` an optional rollback method. Typically for a rollback method to work, you'll need to store some
  state in the class.

So here is our *runner* class:
::

    class ServiceRouterRunner(CookbookRunnerBase):
        def __init__(args, spicerack):
            # args here is the result of CookbookBase.argument_parser().parse_args()
            self.service = args.service
            self.datacenter = args.datacenter
            self.action = args.action
            self.discovery = spicerack.discovery(self.service)
            # Save the initial state for eventual rollback
            state = self.discovery.active_datacenters
            self.was_pooled = self.datacenter in state[self.service]

        def runtime_description(self) -> str:
            return f"{self.action} service {self.service} in {self.datacenter}"

        def run(self):
            if self.action == "pool":
                self.discovery.pool(self.datacenter)
            else:
                self.discovery.depool(self.datacenter)

        def rollback(self):
            if self.was_pooled:
                self.discovery.pool(self.datacenter)
            else:
                self.discovery.depool(self.datacenter)


If the ``run`` method returns a non-zero exit code or raises any exception the optional ``rollback`` method will be
called to allow the cookbook to perform any cleanup action. Any exception raised by the ``rollback`` method will be
logged and the cookbook will exit with a reserved exit code.

The derived classes can have any name and multiple cookbooks in the same module are supported.

Module interface
""""""""""""""""

A simple function-based API interface for the cookbooks in which each cookbook is a Python module that defines the
following constants and functions.

.. module:: cookbook-module

.. attribute:: __title__

   A module attribute that defines the cookbook title. It must be a single line string.

   :type: str

.. function:: argument_parser() -> argparse.ArgumentParser:

   Optional module function to define if the cookbook should accept command line arguments.

   If defined the returned argument parser will be used to parse the cookbook's arguments.

   If not defined it means that the cookbook doesn't accept any argument and if called with arguments it's considered
   an error.

   Cookbooks are encouraged to define an ``argument_parser()`` function so that an help message is automatically
   available with ``-h/--help`` and it can be shown both when running a cookbook directly or in the interactive menu.

   :returns: the argument parser instance.
   :rtype: argparse.ArgumentParser

.. function:: run(args, spicerack)

   Mandatory module function with the actual execution of the cookbook.

   :param args: the parsed arguments that were parsed using the defined ``argument_parser()`` module function or
        :py:data:`None` if the cookbook doesn't support any argument.
   :type args: argparse.Namespace or None
   :param spicerack: the Spicerack accessor instance with which the cookbook can access all the Spicerack capabilities.
   :type spicerack: spicerack.Spicerack
   :returns: the return code of the cookbook, it should be zero or :py:data:`None` on success, a positive integer
        smaller than ``128`` and not in the range ``90-99`` (see :ref:`Reserved exit codes<reserved-codes>`) in case of
        failure.
   :rtype: int or None

Logging
^^^^^^^

The logging is already pre-setup by the ``cookbook`` entry point script that initialize the root logger, so that each
cookbook can just initialize its own :py:mod:`logging` instance and log.

A special logger to send notification to the ``#wikimedia-operations`` IRC channel with the ``!log`` prefix is also
available through the ``spicerack`` argument, passed to the cookbook's ``run()`` function for the module API or
available in the cookbook class as ``self.spicerack`` for the class API, in its ``sal_logger`` property. An additional
``irc_logger`` logger is also available to just write to the ``#wikimedia-operations`` IRC channel.

Both IRC loggers log to both IRC and the nomal log outputs of Spicerack. If the dry-run mode is set it does not log
to IRC.

Log files
"""""""""

The log files can be found in ``/var/log/spicerack/${PATH_OF_THE_COOKBOOK}`` on the host where the cookbooks are run.
All normal log messages are sent to two separate files, of which one always logs at ``DEBUG`` level even if
``-v/--verbose`` is not set.
So for example running the cookbook ``foo.bar.baz`` will generate two log files::

    /var/log/spicerack/foo/bar/baz.log  # with INFO and higher log levels
    /var/log/spicerack/foo/bar/baz-extended.log  # with all log levels

If the cookbook is started with a directory of multiple cookbooks then the logs are all concentrated in the directory
path ones::

    /var/log/spicerack/foo/bar.log  # with INFO and higher log levels
    /var/log/spicerack/foo/bar-extended.log  # with all log levels

Example
"""""""

::

   import logging

   logger = logging.getLogger(__name__)

   logger.info('message')  # this goes to stdout in the operator shell and is logged in both files.
   logger.debug('message') # this goes to stdout in the operator shell only if -v/--verbose is set and is logged only
                           # in the extended file.

   def run(args, spicerack):
       spicerack.irc_logger.info('message')  # This sends a message to the #wikimedia-operation IRC channel with:
                                             # !log user@host message

Spicerack library
^^^^^^^^^^^^^^^^^

All the available modules in the Spicerack package are exposed to the cookbooks through the ``spicerack`` instance
injected in the cookbook. It offers helper methods to obtain initialized instances of all the available libraries.
This instance exposes also some of the global CLI arguments parsed by the ``cookbook`` entry point script such as
``dry_run`` and ``verbose`` as getters. See :py:class:`spicerack.Spicerack` for more details.

Exception handling
^^^^^^^^^^^^^^^^^^

In general each module in the :py:mod:`spicerack` package has its own exception class to raise specific errors, and
all of them are derived from the base class :py:class:`spicerack.exceptions.SpicerackError`.

.. _reserved-codes:

Reserved exit codes
^^^^^^^^^^^^^^^^^^^

Cookbook exit codes in the range ``90-99`` are reserved by Spicerack and must not be used by the cookbooks.
The currently defined reserved exit codes are documented in the :py:mod:`spicerack.cookbook` module.
