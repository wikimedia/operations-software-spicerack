Spicerack Changelog
-------------------


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


.. _`T213296`: https://phabricator.wikimedia.org/T213296
.. _`T219640`: https://phabricator.wikimedia.org/T213296

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
