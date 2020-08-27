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
are technically allowed.

Example of cookbooks tree::

    cookbooks
    |-- __init__.py
    |-- top_level_cookbook.py
    |-- group1
    |   |-- __init__.py
    |   `-- important_cookbook.py
    `-- group2
        |-- __init__.py
        `-- subgroup1
            |-- __init__.py
            `-- some_task.py

API interface
^^^^^^^^^^^^^

Each cookbook must define:

* A title setting a string variable ``__title__`` at the module-level with the desired static value.

* An optional ``argument_parser() -> argparse.ArgumentParser`` function that accepts no arguments and return the
  :py:class:`argparse.ArgumentParser` instance to use to parse the arguments of the cookbook. This function is
  optional, if not defined it means that the cookbook doesn't accept any argument. If a cookbook without that doesn't
  define an ``argument_parser()`` function is called with CLI arguments it's considered an error.

* A ``run(args, spicerack)`` function to actually execute the cookbook, that accept two arguments and returns an
  :py:class:`int` or :py:data:`None`:

  * Argument ``args (argparse.Namespace, None)``: the parsed CLI arguments according to the parser returned by the
    ``argument_parser()`` function or :py:data:`None` if no CLI arguments were passed and the cookbook doesn't define
    an ``argument_parser()`` function. Cookbooks are encouraged to define an ``argument_parser()`` function so that an
    help message is automatically available with ``-h/--help`` and it can be shown both when running a cookbook
    directly or in the interactive menu.
  * Argument ``spicerack (spicerack.Spicerack)``: an instance of :py:class:`spicerack.Spicerack` initialized based on
    the generic CLI arguments parsed to the ``cookbook`` entry point script. It allows to access all the libraries
    available in the ``spicerack`` package.
  * Return value (:py:class:`int`): it must be ``0`` or :py:data:`None` on success and a positive integer smaller than
    ``128`` on failure. The exit codes ``90-99`` are reserved by the ``cookbook`` entry point script and should not be
    used.

Logging
^^^^^^^

The logging is already pre-setup by the ``cookbook`` entry point script that initialize the root logger, so that each
cookbook can just initialize its own :py:mod:`logging` instance and log. A special logger to send notification to the
``#wikimedia-operations`` IRC channel is also available through the ``spicerack`` argument passed to the cookbook's
``run()`` function in its ``irc_logger`` property.
The log files can be found in `/var/log/spicerack/${PATH_OF_THE_COOKBOOK}` on the host where the cookbooks are run.
All normal log messages are sent to two separate files, of which one always logs at ``DEBUG`` level even if
``-v/--verbose`` is not set.
So for example running the cookbook ``foo.bar.baz`` will generate two log files::

    /var/log/spicerack/foo/bar/baz.log  # with INFO and higher log levels
    /var/log/spicerack/foo/bar/baz-extended.log  # with all log levels

If the cookbook is started with a directory of multiple cookbooks then the logs are all concentrated in the directory
path ones::

    /var/log/spicerack/foo/bar.log  # with INFO and higher log levels
    /var/log/spicerack/foo/bar-extended.log  # with all log levels

Example of logging::

    import logging

    logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

    logger.info('message')  # this goes to stdout in the operator shell and is logged in both files.
    logger.debug('message') # this goes to stdout in the operator shell only if -v/--verbose is set and is logged only
                            # in the extended file.

    def run(args, spicerack):
        spicerack.irc_logger.info('message')  # This sends a message to the #wikimedia-operation IRC channel with:
                                              # !log user@host message

Spicerack library
^^^^^^^^^^^^^^^^^

All the available modules in the Spicerack package are exposed to the cookbooks through the ``spicerack`` argument to
the ``run()`` function, that offers helper methods to obtain initialized instances of all the available libraries.
This instance exposes also some of the global CLI arguments parsed by the ``cookbook`` entry point script such as
``dry_run`` and ``verbose`` as getters. See :py:class:`spicerack.Spicerack` for more details.

Exception handling
^^^^^^^^^^^^^^^^^^

In general each module in the :py:mod:`spicerack` package has its own exception class to raise specific errors, and
all of them are derived from the base :py:class:`spicerack.exceptions.SpicerackError`.
