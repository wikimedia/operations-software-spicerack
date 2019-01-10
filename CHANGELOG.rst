Spicerack Changelog
-------------------


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

.. _`T213296`: https://phabricator.wikimedia.org/T213296