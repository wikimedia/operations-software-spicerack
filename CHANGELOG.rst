Spicerack Changelog
-------------------


`v0.0.30`_ (2020-02-11)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* netbox: rename injected property in host details (`T231068`_).

  * When fetching host details from Netbox, Spicerack injects some properties to distinguish between virtual and
    physical hosts. Renaming the ``cluster_name`` property to ``ganeti_cluster`` to avoid possible confusions.

New features
""""""""""""

* spicerack: add getter for the Netbox master host. In some cases is necessary to execute commands on the Netbox master
  host, add a getter to resolve its real hostname (`T231068`_).

* ganeti: add cluster to ``instance()`` (`T231068`_).

  * Allow to specify the Ganeti cluster name when calling ``instance()``. If set the instance will be searched only in
    that cluster.
  * Pass the cluster name to the ``GntInstance`` constructor and expose it via a getter to remove the necessity to look
    it up separately when cluster was not passed to ``instance()`` for auto-detection.

* ganeti: add initial support for ``gnt-instance`` (`T231068`_).

  * Add initial support for ``gnt-* commands`` to be executed on the cluster master via remote execution.
  * Add initial support for ``gnt-instance`` commands to perform Ganeti VMs decommissioning, in particular:

    * ``shutdown``: to shutdown a Ganeti VM, with its optional ``timeout`` parameter.
    * ``remove``: to shutdown and remove a Ganeti VM, with its optional ``shutdown_timeout`` parameter.

Minor improvements
""""""""""""""""""

* mediawiki: use Cumin alias instead of role query (`T243935`_).

Miscellanea
"""""""""""

* dnsdisc: fix typo in docstring.

`v0.0.29`_ (2020-01-16)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* mediawiki: in ``stop_cronjobs()`` adapt for the migration from ``hhvm`` to ``php-fpm`` in  production (`T229792`_).
* dnsdisc: use port ``5353`` to query the resolvers. The authdns part is answering to port ``5353`` from now on.
* dns: allow to specify a custom port for the resolver. The authdns part is answering to port ``5353`` from now on,
  allow to specify a custom port when instantiating a new ``Dns`` recursor.
* ganeti: Add ``esams``, ``ulsfo`` and ``eqsin`` clusters and rows definitions.

Bug Fixes
"""""""""

* ipmi: the change introduced via `I4d4ade351493a548e9e7a578bf9a7acbb45a5c0`_ to use ``subprocess.run()`` created a
  regression causing the ``ipmi`` calls to no longer capture stdout. Restored normal behaviour (`T147074`_).

Miscellanea
"""""""""""

* dns: remove unused type hint ignore comments.
* remote: fix docstring return type.
* documentation: updated link to the requests module documentation.
* docstrings: fix pep257 reported errors.
* mypy: Get rid of no longer needed ``# type: ignore`` annotations that are now detected automatically by ``mypy``.

`v0.0.28`_ (2019-10-10)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* netbox: Transparently support read-only operations for virtual machines (`T231068`_).
* ganeti: Add ability to get ganeti cluster for given instance (`T231068`_).
* ipmi: add support for channel 2.
* ipmi: use ``subprocess.run()`` instead of ``subprocess.check_output()``.

`v0.0.27`_ (2019-08-25)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* remote: Move splitting of a ``RemoteHosts`` instance to a ``split()`` method.
* netbox: Make host private and raise exception on not found.
* netbox: Add method to return host information.


`v0.0.26`_ (2019-08-06)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Add Netbox module
* Add the ``LBRemoteCluster`` class to manage cluster behind a load balancer

Minor improvements
""""""""""""""""""

* icinga: Add a function to force a recheck of all sevices
* confctl: Add ``filter_objects`` and ``update_objects``
* confctl: add ``change_and_revert`` contextmanager

Bug Fixes
"""""""""

* elasticsearch_cluster: correct ports for relforge cluster
* elasticsearch_cluster: fix ``mypy`` newly reported bug
* tests: fix ``pytest`` ``caplog`` matching
* tests: fix ``pep257`` newly reported issues

`v0.0.25`_ (2019-05-10)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* setup.py: fix ``urllib3`` dependency

  * In order to build on Debian Stretch without backported packages, relax a bit the urllib3 dependency as the only
    goal for to specify it is to avoid conflicts with the latest version.

* documentations: fix Sphinx configuration

  * In order to avoid issues while building the Debian package on Stretch where Sphinx ``1.4.9`` is available, change
    configuration to:

    * Reduce minimum Sphinx version to ``1.4.9`` in ``setup.py``
    * Remove the ``warning-is-error`` configuration from ``setup.cfg`` that is applied to every Sphinx run, and move
      it directly into ``tox.ini`` as a command line ``-W`` option, that will be executed only by ``tox`` and not
      during the Debian package build process.

`v0.0.24`_ (2019-05-09)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* prometheus: add timeout support to ``query()`` method
* ganeti: add timeout support
* cookbook API: drop ``get_title()`` support

  * No current cookbook is using the dynamic way to provide a title through ``get_title(args)``
  * This abstraction has not proven to be useful and the fact to mangle dynamically the title of a cookbook based on
    the current parameter while you can then execute it with different ones doesn't seem very useful, dropping it
    completely from the Cookbook API

* doc: mark Sphinx warnings as error

  * To make the documentation building process more robust make Sphinx fail on warnings too
  * This requires ``Sphinx > 1.5`` and will require to use the backport version while building the package on Debian Stretch

* doc: add checker to ensure modules are documented

  * It's common when adding a new module to forget to add the few bits required to auto-generated its documentation
  * Add a check to ensure that all Spicerack modules are listed in the documentation API index and that the linked
    files exists

Bug Fixes
"""""""""

* ganeti: Fix RAPI port
* prometheus: fix base URL template
* doc: autodoc missing API modules

Miscellanea
"""""""""""

* setup.py: force ``urllib3`` version due to ``pip`` bug
* Add emacs ignores to gitignore
* tests: temporarily force ``bandit < 1.6.0``

    * Due to a bug upstream bandit 1.6.0 doesn't honor the excluded directories, causing the failure of the bandit tox
      environments. Temporarily forcing its version

`v0.0.23`_ (2019-04-19)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Add basic Ganeti RAPI support
* Add basic Prometheus support

Minor improvements
""""""""""""""""""

* elasticsearch: add reset all indices to read/write capability (`T219799`_)

Bug Fixes
"""""""""

* elasticsearch: logging during shard allocation was too verbose, some messages lowered to debug level

Miscellanea
"""""""""""

* flake8: enforce import order and adopt ``W504``

  * Add ``flake8-import-order`` to enforce the import order using the ``edited`` style that corresponds to our
    styleguide, see: `mediawiki.org: Coding_conventions/Python`_
  * Mark spicerack as local and do not specify any organization-specific packages to avoid to keep a manually curated
    list of packages
  * Fix all out of order imports
  * For line breaks around binary operators, adopt ``W504`` (breaking before the operator) and ignore ``W503``, following PEP8 suggestion, see: `PEP0008#line_break_binary_operator`_
  * Fix all line breaks around binary operators to follow ``W504``


`v0.0.22`_ (2019-04-04)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

elasticsearch: use NodesGroup instead of free form JSON


`v0.0.21`_ (2019-04-03)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* elasticsearch: Retrieve hostname and fqdn from node attributes
* elasticsearch: make unfreezing writes more robust (`T219640`_)
* elasticsearch: cleanup test by introducing a method to mock API calls
* elasticsearch: rename elasticsearchclusters to elasticsearch_clusters

Bug Fixes
"""""""""

* tox: fix typo in environment name

Miscellanea
"""""""""""

* Add Python type hints and mypy check, not for variables and properties as we're still supporting Python 3.5
* setup.py: revert commit 3d7ab9b that forced the ``urllib3`` version installed as it's not needed anymore
* tests/docs: unify usage of ``example.com`` domain

`v0.0.20`_ (2019-03-06)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* ipmi: add password reset functionality

Minor improvements
""""""""""""""""""

* elasticsearch: upgrade rows one after the other
* remote: suppress Cumin's output. As a workaround for a regression in colorama for stretch
* Expose hostname from Reason.
* elasticsearch: use the admin Reason to get current hostname

Bug Fixes
"""""""""

* debmonitor: fix missing variable for logging line
* elasticsearch: fix typo (xarg instead of xargs)
* doc: fix reStructuredText formatting

Miscellanea
"""""""""""

* Drop support for Python 3.4
* Add support for Python 3.7
* tests: refactor tox environments

`v0.0.19`_ (2019-02-21)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch: support cluster names which have ``-`` in them.
* elasticsearch: ``get_next_clusters_nodes()`` raises ``ElasticsearchClusterError``.
* elasticsearch: systemctl iterates explicitly on elasticsearch instances.

Miscellanea
"""""""""""

* setup.py: add ``long_description_content_type``.

`v0.0.18`_ (2019-02-20)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch: access production clusters over HTTPS.

`v0.0.17`_ (2019-02-20)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* icinga: add ``remove_on_error`` parameter to the ``hosts_downtimed()`` context manager to decide wether to remove
  the downtime or not on error.

Bug Fixes
"""""""""

* elasticsearch: raise logging level to ERROR for elasticsearch
* elasticsearch: retry on all urllib3 exceptions

`v0.0.16`_ (2019-02-18)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch: retry on TransportError while waiting for node to be up
* Change !log formatting to match Stashbot expectations.

`v0.0.15`_ (2019-02-14)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch: add doc type to delete query.

`v0.0.14`_ (2019-02-13)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* icinga: add context manager for downtimed hosts:

  * Add a context manager to allow to execute other commands while the hosts are downtimed, removing the downtime at the end.

* management: add management module:

  * Add a management module with a ``Management`` class to interact with the management console names.
  * For now just add a ``get_fqdn()`` method to automatically calculate the management FQDN for a given hostname.

* puppet: add ``check_enabled()`` and ``check_disabled()`` methods.
* decorators: make ``retry()`` DRY-RUN aware:

  * When running in DRY-RUN mode no real changes are done and usually the ``@retry`` decorated methods are checking
    for some action to be propagated or completed. Hence when in DRY-RUN mode they tend to fail and retry until the
    *tries* attempts are exhausted, adding unnecessary time to the DRY-RUN.
  * With this patch the ``retry()`` decorator is able to automagically detect if it's a DRY-RUN mode when called by
    any instance method that has a ``self._dry_run`` property or, in the special case of ``RemoteHostsAdapter``
    derived instances, it has a ``self._remote_hosts._dry_run`` property.

* puppet: add ``delete()`` method to remove a host from PuppetDB and clean up everything on the Puppet master.
* spicerack: expose the ``icinga_master_host`` property.
* administrative: add ``owner`` getter to Reason class:

  * Add a public getter for the owner part of a reason, that retuns in a standard format the user running the code and the host where it's running.

Minor improvements
""""""""""""""""""

* decorators: improve tests.
* documentation: fine-tune generated documentation.

Bug Fixes
"""""""""

* dns: remove unused ``dry_run`` argument.
* Add missing timeout to requests calls.
* dns: fix logging message.
* elasticsearch_cluster: change ``is_green()`` implementation.
* elasticsearch_cluster: fix issues found during live tests.
* spicerack: fix ``__version__``.
* ipmi: fix typos in docstrings.

`v0.0.13`_ (2019-01-14)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* remote: fix logging for ``reboot()``.

`v0.0.12`_ (2019-01-10)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* ipmi: add support for DRY RUN mode
* config: add load_ini_config() function to parse INI files.
* debmonitor: use the existing configuration file

  * Instead of requiring a new configuration file, use the existing one already setup by Puppet for the debmonitor
    client.
  * Inject the path of the Debmonitor config into the ctor with a default value.

* puppet: add default ``batch_size`` when running puppet

  * Allow to specify the ``batch_size`` when running puppet on a set of hosts.
  * Add a default ``batch_size`` to avoid to overload the Puppet master hosts.

Bug Fixes
"""""""""

* phabricator: remove unneded pylint ignore
* mediawiki: update maintenance host Cumin query
* remote: add workaround for Cumin bug

  * To avoid unnecessary waiting on the most common use case of ``reboot()``, that is with only one host, unset the
    default ``batch_sleep`` as a workaround for `T213296`_.

* puppet: fix regenerate_certificate()

  * When re-generating the certificate, Puppet will exit with status code ``1`` both if successful or on failure.
  * Restrict the accepted exit codes to ``1``.
  * Detect errors in the output and raises if any.

`v0.0.11`_ (2019-01-08)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* debmonitor: add debmonitor module
* phabricator: add phabricator module

Bug Fixes
"""""""""

* icinga: fix ``command_file`` property
* puppet: fix ``subprocess`` call to ``check_output()``
* dns: include ``NXDOMAIN`` in the ``DnsNotFound`` exception
* admin_reason: fix default value for task

`v0.0.10`_ (2018-12-19)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* cookbook: split main into ``argument_parser()`` and ``run()``.
* remote: refactor ``Remote.query()`` API.

New features
""""""""""""

* Add administrative module.
* dns: add dns module.
* Add elasticsearch_cluster module.
* Add Icinga module.
* Add ipmi module.
* Add Puppet module.
* puppet: add additional methods to ``PuppetHosts``.
* puppet: add PuppetMaster class.
* remote: add more host functionalities.

Minor improvements
""""""""""""""""""

* doc: add documentation and its generation.
* interactive: add ``ensure_shell_is_durable()``.

Bug Fixes
"""""""""

* administrative: fix Reason's signature
* elasticsearch_cluster: fix tests for Python 3.5.
* icinga: fix typo in test docstring.
* interactive: check TTY in ``ask_confirmation()``.
* mediawiki: kill also HHVM on stop_cronjobs.
* Fix typo in README.rst.
* tests: fix randomly failing pylint check.

Miscellanea
"""""""""""

* setup.py: update curator version to match our current elasticsearch version.
* setup.py: force ``urllib3`` version.
* tests: fix lint ignore.


`v0.0.9`_ (2018-09-12)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* mediawiki: improve siteinfo checks.
* dnsdisc: improve TTL checks.
* exceptions: add ``SpicerackCheckError``.
* tests: improve prospector tests.

Bug Fixes
"""""""""

* dnsdisc: catch dnspython exceptions.
* setup.py: add missing fields and fix missing comma.

`v0.0.8`_ (2018-09-10)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* mediawiki: ignore exit codes on stop_cronjobs.
* logging: minor improvements and a fix.

`v0.0.7`_ (2018-09-06)
^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* dnsdisc: fix dry-run in ``check_if_depoolable()``.

`v0.0.6`_ (2018-09-06)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* log: remove relic from switchdc.
* mysql: refactor sync check to avoid GTID.

`v0.0.5`_ (2018-09-05)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* mediawiki: improve validation checks.

`v0.0.4`_ (2018-09-04)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Add redis_cluster module.
* dnsdisc:

  * add methods for checking if a datacenter can be depooled.
  * add a ``pool()`` and ``depool()`` methods.

* mediawiki:

  * improve ``stop_cronjobs()`` method.
  * add ``check_cronjobs_disabled()`` method.
  * refactor to use confctl's ``set_and_verify()``.
  * split ``set_readonly()`` and add checks.

* mysql:

  * add ``get_dbs()`` method.
  * rename the ``ensure_core_masters_in_sync()`` method.

* confctl: add ``set_and_verify()`` method.

`v0.0.3`_ (2018-08-30)
^^^^^^^^^^^^^^^^^^^^^^

Miscellanea
"""""""""""

* Change PyPI package name and add long description to ``setup.py``.

`v0.0.2`_ (2018-08-28)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* mediawiki: add siteinfo-related methods.

`v0.0.1`_ (2018-08-26)
^^^^^^^^^^^^^^^^^^^^^^

* Initial version.

.. _`mediawiki.org: Coding_conventions/Python`: https://www.mediawiki.org/wiki/Manual:Coding_conventions/Python#Imports
.. _`PEP0008#line_break_binary_operator`: https://www.python.org/dev/peps/pep-0008/#should-a-line-break-before-or-after-a-binary-operator

.. _`I4d4ade351493a548e9e7a578bf9a7acbb45a5c0`: https://gerrit.wikimedia.org/r/q/I4d4ade351493a548e9e7a578bf9a7acbb45a5c0

.. _`T147074`: https://phabricator.wikimedia.org/T147074
.. _`T213296`: https://phabricator.wikimedia.org/T213296
.. _`T219640`: https://phabricator.wikimedia.org/T213296
.. _`T219799`: https://phabricator.wikimedia.org/T219799
.. _`T229792`: https://phabricator.wikimedia.org/T229792
.. _`T231068`: https://phabricator.wikimedia.org/T231068
.. _`T243935`: https://phabricator.wikimedia.org/T243935

.. _`v0.0.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.1
.. _`v0.0.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.2
.. _`v0.0.3`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.3
.. _`v0.0.4`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.4
.. _`v0.0.5`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.5
.. _`v0.0.6`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.6
.. _`v0.0.7`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.7
.. _`v0.0.8`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.8
.. _`v0.0.9`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.9
.. _`v0.0.10`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.10
.. _`v0.0.11`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.11
.. _`v0.0.12`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.12
.. _`v0.0.13`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.13
.. _`v0.0.14`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.14
.. _`v0.0.15`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.15
.. _`v0.0.16`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.16
.. _`v0.0.17`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.17
.. _`v0.0.18`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.18
.. _`v0.0.19`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.19
.. _`v0.0.20`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.20
.. _`v0.0.21`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.21
.. _`v0.0.22`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.22
.. _`v0.0.23`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.23
.. _`v0.0.24`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.24
.. _`v0.0.25`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.25
.. _`v0.0.26`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.26
.. _`v0.0.27`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.27
.. _`v0.0.28`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.28
.. _`v0.0.29`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.29
.. _`v0.0.30`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.30
