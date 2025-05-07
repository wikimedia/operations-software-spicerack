Introduction
============


.. include:: ../../README.rst


Cookbooks
---------

The cookbooks are the user facing units of automation. There is a collection of cookbooks to automate and orchestrate
operations in the WMF infrastructure. The cookbooks are executed by the ``cookbook`` binary provided by the
``spicerack`` package.

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

The ``__title__`` and ``__owner_team__`` properties of the `Module interface`_ can also be used in the ``__init__.py``
files of cookbook packages (directories). The ``__title__`` will set the title of the cookbook package and the
``__owner_team__`` will set the owner for all the cookbooks in the package and eventual subpackages, unless overridden
by specific cookbooks or subpackages. If the ``__title__`` variable is not set the first line of the module docstring
will be used, if present.

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
        def __init__(self, args, spicerack):
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

   A module attribute that defines the cookbook title. It must be a single line string. If not present and the module
   has a top level docstring, the first line of the docstring will be used as title.

   :type: str

.. attribute:: __owner_team__

   Name of the team owning this cookbook and responsible to keep it up to date. If unset and any parent package
   (directory of cookbooks) has the ``__owner_team__`` property set it will inherit it. It shows up when listing
   cookbooks and in the help message as parser epilog. When set on an ``__init__.py`` file of a cookbooks package
   (directory of cookbooks) it will set the ownership for all cookbooks in the package unless overridden in the
   specific cookbooks.

   :type: str

.. attribute:: MAX_CONCURRENCY

   Optional module attribute that defines how many parallel runs of the cookbook are allowed. If not set the value
   defined in :py:attr:`spicerack.cookbook.CookbookRunnerBase.max_concurrency` will be used.

   :type: int

.. attribute:: LOCK_TTL

   Optional module attribute that defines the concurrency lock time to live (TTL) in seconds. For each concurrent run
   a lock is acquired for this amount of seconds. If not set the value defined in
   :py:attr:`spicerack.cookbook.CookbookRunnerBase.lock_ttl` will be used.

   :type: int

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
The wmflib's :py:class:`wmflib.interactive.notify_logger` is configured to notify users on the
``#wikimedia-operations`` IRC channel based on the Spicerack's configuration flag ``user_input_notifications_enabled``.

Both IRC loggers log to both IRC and the nomal log outputs of Spicerack. If the dry-run mode is set it does not log
to IRC nor notify the user when awaiting for input.

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

When using :py:meth:`spicerack.Spicerack.run_cookbook` to call other cookbooks from within a cookbook, all logs will
go to the parent cookbook log files.

Log files are automatically rotated when they reach 10 MB in size and up to 500 rotated files are kept for auditing
purposes.

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
                                             # user@host message
       spicerack.sal_logger.info('message')  # This sends a message to the #wikimedia-operation IRC channel with:
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

.. _distributed-locking:

Distributed locking
^^^^^^^^^^^^^^^^^^^

Spicerack supports also distributed locking to prevent some actions from being executed multiple times in parallel in
the environments with etcd configured. Each lock can be defined with arbitraty concurrency and TTL (time to live). That
means that each lock can either be exclusive or allow a given number of parallel executions. The locks are saved in
etcd.

The locking support can be globablly enabled/disabled via configuration file and can also be disabled on a given
cookbook run via the ``--no-locks`` command line flag. This can be used in an emergency if unable to acquire locks or
if there are issues with the locking backend.

Spicerack will automatically retry for half an hour to acquire a lock if there is no slot available for the given key
and concurrency, listing which are the holders of the exiting locks for the same key in the form ``user@host [PID]``.

Example output in case of being unable to acquire the lock::

    [1/27, retrying in 5.00s] Unable to acquire lock: {'concurrency': 1, 'created': '2023-10-19 12:52:06.006568', 'owner': 'user1@cumin2002 [249024]', 'ttl': 300} for key /spicerack/locks/cookbooks/sre.dns.netbox.
    There are already 1 concurrent locks and the concurrency allowed is 1:
          2023-10-19 12:52:05.985199: user2@cumin1001 [340699]

There are three types of locks:

* **Spicerack locks**: acquired by Spicerack modules around specific lines of code that are deemed critical and require a
  dedicated lock.
* **Cookbooks custom locks**: locks created by the cookbooks using the Spicerack accessor
  :py:meth:`spicerack.Spicerack.lock` around specific lines of code.
* **Automatic cookbook locks for each run**: Spicerack acquires a lock for each cookbook run with the cookbook full name
  as key (e.g. ``sre.hosts.name``). By default it uses the concurrency and TTL defined in
  :py:attr:`spicerack.cookbook.CookbookRunnerBase.max_concurrency` and
  :py:attr:`spicerack.cookbook.CookbookRunnerBase.lock_ttl` respectively. The cookbook can customize these parameters
  in two different ways:

  * **Static override**: just overriding the ``max_concurrency`` and ``lock_ttl`` class properties in the cookbook runner
    class will make the lock be acquired with these parameters.
  * **Dynamic override**: for a more in-depth customization, the cookbook runner class can override the
    :py:attr:`spicerack.cookbook.CookbookRunnerBase.lock_args` instance property to dynamically return a
    :py:attr:`spicerack.cookbook.LockArgs` instance based on any live argument. This way the cookbook can also provide
    a custom key suffix to use for the lock key, allowing to hold a different lock based on the use case. For example:

    * If the cookbook has a read-only (e.g. check, list, etc.) and a read-write (e.g. create, update, delete) mode of
      operation, it could set the ``max_concurrency`` to ``0`` when executed in read-only mode and to ``1`` or a very
      low value when executed in read-write mode.
    * If the cookbook targets a specific host/cluster it could use the host/cluster name as suffix so that the lock
      will be per-host/cluster. An unlimited concurrent runs of the cookbook can be made with different hosts/clusters
      but for example it could limit to only one concurrent run of the cookbook for any given host/cluster.::

        @property
        def lock_args(self):
            """Make the cookbook lock per-cluster."""
            return LockArgs(suffix=self.cluster, concurrency=1, ttl=600)
