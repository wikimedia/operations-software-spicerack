Spicerack Changelog
-------------------

`v2.0.0`_ (2022-02-15)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* management: removed module, it was deprecated in v1.0.0.

New features
""""""""""""

* spicerack: allow to execute another cookbook from within a cookbook.

  * Add the capability from within a cookbook to call another cookbook with custom parameters using the
    ``run_cookbook()`` method in the Spicerack class.
  * The called cookbook will be executed with the same global options with which the current cookbook is running with
    and will log in the same file of the current cookbook run.

Minor improvements
""""""""""""""""""

* redfish: better support of parsing JSON responses (`T299123`_).

  * In some older Dell servers the Redfish API sometimes replies with different casing for the ``MessageId`` key, like
    ``MessageID``.
  * It's also possible that Oem custom messages are reported in the same replies with a different structure.
  * Skip the Oem messages and try both keys cases when parsing the reply.

* redfish: improve support for DRY-RUN mode.

  * In DRY-RUN mode allow read-only requests to be performed (only GET and HEAD) but return a dummy successful
    responses in case of an exception raised by requests (timeout, connection error, etc).
  * In DRY-RUN mode don't allow read-write requests and return a successful dummy response instead.
  * In various methods return a dummy response in DRY-RUN mode.

* dhcp: case-insensitive match of the serial number for the Dell management DHCP requests.

 * When matching the serial number in the DHCP request for the management interfaces of Dell servers, match them in a
   case-insensitive way because the data sent varies between hosts (``idrac-ABC1234`` or ``iDRAC-ABC1234``).

Miscellanea
"""""""""""

* setup.py: the latest v2.2.0 release of dnspython is generating mypy issues, temporarily put an upper limit to it.
* spicerack: adapt type hint to the latest wmflib release.

`v1.1.1`_ (2021-12-22)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* redfish: tell if any change was made in ``DellSCP`` instances:

  * When updating a ``DellSCP`` configuration with the ``set()`` or ``update()`` method, return ``True`` if the config
    was actually changed, ``False`` if it had already the correct value(s).

Bug fixes
"""""""""

* dhcp: fix file removal check in dry-run mode.

`v1.1.0`_ (2021-12-16)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* spicerack.redfish: add new module with support for Redfish API:

  * Add a new redfish module that allows to interact with the Redfish API. As Redfish implementation differs
    sensibly between vendors, there are some basic functionalities in the ``Redfish`` class and then there is a
    ``RedfishDell`` class for Dell-specific functionalities.
  * At the moment the only supported vendor is Dell (hence the hardcoded ``RedfishDell`` call in
    ``Spicerack.redfish()``.

* spicerack: add a ``management_password`` property getter to access the cached management password. If the cache is
  empty the password will be asked to the user.

Minor improvements
""""""""""""""""""

* ganeti: add new Ganeti clusters in the new site ``drmrs``.

Bug fixes
"""""""""

* ipmi: when running an IPMI command that contains sensitive data, allow to hide the sensitive data from the logs and
  the outputs.
* ganeti: fix up row configuration for ganeti test cluster.
* dhcp: fix missing semicolon in DHCP config.
* remote: intercept bad uptimes in ``wait_reboot_since()``.

  * In some cases the uptime method could fail to parse the host uptime, for example during a shutdown of a system
    where the login might be prevented to the host.
  * Make sure that the ``wait_reboot_since()`` method catches those errors too and retries.

Miscellanea
"""""""""""

* Adopt ``pathlib.Path`` instead of the ``os`` and ``os.path`` functions across the project to modernize it following
  current best practices.
* administrative: add examples to the documentation and documentation for the special method ``__str__``.
* pylint: fix newly reported issues.

`v1.0.6`_ (2021-10-21)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* dhcp: add support for MAC address based config (`T269855`_):

  * Add support for MAC address based configuration snippets to be used in the automation for Ganeti VMs instead of
    using DHCP Option 82 as the MAC address is retrieved from Ganeti API.
  * The MAC address is validated to ensure has the format accepted by the DHCP server.
  * Consolidate the filename path for both DHCP Option 82 and MAC address based configuration to be in the same
    directory, dependent only by the TTY settings as there is no other difference between the two and it allows to
    prevent duplicated snippets for the same hostname in different directories as the library checks that the file
    doesn't exists before creating it.
  * Consolidate the defult string representation implementation of the DHCPConfiguration derived classes into the
    abstract parent one because they are all the same. Define a class property ``_template`` as part of the
    ``DHCPConfiguration`` class API.

Minor improvements
""""""""""""""""""

* mediawiki: add a ``get_primary_dc()`` method that returns the primary/active datacenter.
* kafka: docstrings minor improvements.

Miscellanea
"""""""""""

* changelog: fix typo in previous entry.

`v1.0.5`_ (2021-10-12)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* kafka: add a new ``kafka`` module with the following capabilities (`T291681`_):

  * transferring of offsets between consumer groups and clusters approximating offsets based on timestamp.
  * approximating and seeking offsets based on user provided timestamps.

Minor improvements
""""""""""""""""""

* icinga: add ``recheck_failed_services()`` method to force a recheck of services which are in failed state.

Bug fixes
"""""""""

* puppet: get only the last line of output in ``PuppetHosts.get_ca_servers()`` to ignore spurious output that might be
  present in some environments.

`v1.0.4`_ (2021-10-06)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* dhcp: use IP address instead of DNS name

  * Given that all the required data comes from Netbox there is no point to depend on the DNS when generating the DHCP
    snippets, require to pass the IPv4 instead of the FQDN.
  * Renamed ``fqdn`` parameter to ``ipv4`` in the ``DHCPConfOpt82`` class.
  * Renamed ``ip_address`` parameter to ``ipv4`` in the ``DHCPConfMgmt`` class.
  * Although technically this is an API change, the whole module is new and still unused except from the experimental
    reimage cookbook, hence not considering it as a breaking change for the semantic versioning.

Minor improvements
""""""""""""""""""

* remote: reduce wait time for reboot to 20 minutes.

`v1.0.3`_ (2021-09-28)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* dhcp: fix typo in opt82 file path.

`v1.0.2`_ (2021-09-27)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* dhcp: always require to se the OS version when instantiating a ``DHCPConfOpt82`` instance. Although technically this
  is an API change, the whole module is new and still unused, hence not considering it as a breaking change.
* remote, puppet: reduce logging verbosity.

Bug fixes
"""""""""

* ganeti: use ``--force`` option in shutdown method when calling ``gnt-instance shutdown`` to work with all states a
  VM can be in.
* puppet: fix check exception inheritance to the correct ``SpicerackCheckError``.

`v1.0.1`_ (2021-09-23)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* remote: refactor ``wait_reboot_since()``

  * As the check for uptime is currently either returning a value for all hosts or raising an exception, remove the
    existing logic to check for a partial result as that can't happen.
  * Catch instead the error and re-raise a check exception with a clear message.
  * Also round the printed value of the uptime and the time against which it's checked to 2 decimal values for more
    readability.

Miscellanea
"""""""""""

* setup.py: limit elasticsearch max version

  * The latest 7.15.0 release has started to deprecate things for the upcoming 8.0.0 release, and mypy started
    complaining about some return types.
  * Instead of fixing the signatures to be compatible with both versions put a max version limit for now, we'll deal
    with the upgrade when the time will come, Debian most recent version is 7.1.0.

`v1.0.0`_ (2021-09-22)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* remote: remove ``RemoteHosts.init_system()`` method:

  * As systemd is used by all hosts and this method is not used in any cookbook, remove it completely as it's no longer
    needed.

New features
""""""""""""

* remote: add support to enable/disable Cumin output:

  * Add support to suppress Cumin's output and progress bars independently to the ``RemoteHosts`` and
    ``LBRemoteCluster`` classes.
  * Add a ``print_output`` and ``print_progress_bars`` boolean parameters to ``run_sync()``, ``run_async()`` and
    ``run()`` methods to independently print Cumin's output and progress bars respectively.
  * Add a simplified ``verbose`` parameter to the more higher level methods ``restart_services()`` and
    ``reload_services()`` that when set to ``False`` will suppress both output and progress bars at once.
  * Add just the ``print_progress_bars`` parameter for the high level methods ``wait_reboot_since()`` and ``uptime()``.
  * All the new parameters default to ``True`` right now to keep the existing behaviour, to be changed to ``False`` in
    a future release.

Minor improvements
""""""""""""""""""

* icinga: reduce verbosity of Cumin's output, taking advantage of the new parameters to control the output of Cumin's
  commands.
* puppet: reduce verbosity of Cumin's output, taking advantage of the new parameters to control the output of Cumin's
  commands.
* dhcp: reduce verbosity of Cumin's output, taking advantage of the new parameters to control the output of Cumin's
  commands.

Bug fixes
"""""""""

ipmi: improve dry-run mode for ``force_pxe()``:

* When ``force_pxe()`` can't verify that the next boot will indeed be via PXE it raises an exception. Convert that
  into a warning logging message when in DRY-RUN mode to let the cookbooks continue the DRY-RUN.

Miscellanea
"""""""""""

* versioning: moving Spicerack releases to a semantic versioning schema.
* management: deprecate the ``Management`` class:

  * As its only purpose was to get the management FQDN of a host, given that the same functionality is now provided
    by the netbox module via the ``NetboxServer`` class and its ``mgmt_fqdn`` and ``asset_tag_fqdn`` properties,
    deprecate the class for a subsequent removal.

* confctl: fix example code in docstring.
* pylint: fix newly reported issues.
* docs: add how to contribute section.

`v0.0.59`_ (2021-09-09)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* ipmi: refactor class signature

  * API breaking change, but the ``Spicerack.ipmi()`` accessor is used only in the ``sre.hosts.decommission`` and
    ``sre.hosts.ipmi-password-reset cookbooks``, so it should be trivial to change both at once.
  * Convert the IPMI class to require the FQDN of the management console to target, to avoid the need to pass that
    around both from the client and internally in the class.
  * The caching of the management password is done transparently by the ``Spicerack.ipmi()`` accessor to avoid the
    anoyance of being asked the management password for each host.

* dhcp: small refactor (the module is still unused)

  * Rename ``switch_port`` to ``switch_iface`` to avoid confusions.
  * Rename the context manager from ``dhcp_push()`` to ``config()`` as it's more natural to use:
    ``with dhcp.config(my_config): # do something``
  * Simplify formatting of templates, added ignores to vulture for false positives
  * Add constructor documentation to the dataclasses.

* icinga: remove the deprecated ``Icinga`` class

  * The Icinga class has been deprecated for a while now and it's time to remove it completely. No cookbook is using
    it anymore.


New features
""""""""""""

* remote: add support for the installer key

  * When instantiating a ``remote()`` instance, allow to pass a new parameter ``installer``, defaulted to ``False``,
    that when ``True`` will use the special installer key for the remote instances that allow to connect to the
    Debian installer environment or a freshly installed host prior to its first Puppet run.

* ipmi: add status and reboot capabilities:

  * Add a new method ``power_status()`` that returns the current power status and is also used by the existing
    ``check_connection()`` method.
  * Add a new method ``reboot()`` to issue an IPMI power on or power cycle, based on the current status of the device.

* netbox: add getter ``asset_tag_fqdn`` for the asset tag mgmt FQDN property.
* icinga: add ``downtime_services()`` and ``remove_service_downtimes()`` and also a ``services_downtimed()`` context
  manager to allow to downtime only the host services that matches the given regex.


Minor improvements
""""""""""""""""""

* puppet: minor improvements

  * Return the results from the ``Puppet.first_run()`` method to allow to save it to a file like the current reimage
    script does.
  * Add an accessor for the ``master_host`` property in the ``PuppetMaster`` class as this is created and instantiated
    by Spicerack and was hidden from the user of the API.

* decorators: migrate to the wmflib version of ``@retry`` (`T257905`_)

  * Use the wmflib version of ``@retry`` while keeping the dry-run awareness and default to catching ``SpicerackError``
    instead of ``WmflibError`` like the pre-exsiting version was doing.

Miscellanea
"""""""""""

* code style: migrate all the usage of string ``format()`` to f-strings.
* pylint: addressed newly reported pylint issues and removed unnecessary disable comments.
* prospector: disable ``E203`` for pep-8 over black.
* code style: if there are no local modifications check last commit instead of not checking anything.

`v0.0.58`_ (2021-08-25)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Class API: add ``rollback()`` method

  * Add a new ``rollback()`` method to the ``CookbookRunnerBase`` base class that by default does nothing.
  * The method is called by Spicerack when a cookbook exits with a non-zero exit code or raises an un-caught exception.
  * This allows cookbooks to define their own cleanup strategy in case of errors, for example to restore a previously
    coherent state.
  * Any exception raised by the ``rollback()`` method will be caught and logged by Spicerack with its original exit
    code and will then exit with a reserved exit code for a failed rollback.

Minor improvements
""""""""""""""""""

* mediawiki: remove cron-specific maintenance implementation details, replaced by systemd timers (`T289078`_).

Bug fixes
"""""""""

* icinga: use shlex to quote the command string for bash (`T288558`_).

  * This fixes the downtiming that would fail if the admin reason contains an apostrophe, due to lack of escaping.

* mediawiki: ignore php-fpm when stopping cronjobs (`T285804`_).

  * On mwmaint, php-fpm is used to serve noc.wikimedia.org so we want to keep it running even when stopping cronjobs.

`v0.0.57`_ (2021-08-02)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* dnsdisc: improved message logged explicitely saying what was checked and what didn't match when checking that a
  discovery record has been updated (`T285706`_).
* icinga: adapt to the newer API of the ``icinga-status`` output.
* icinga: write directly to the Icinga command file instead of calling the ``icinga-downtime`` wrapper script where
  it was used so that the whole module now interacts directly with the Icinga command file. This opens up the route
  for further improvements (`T285803`_).
* ganeti: add ganeti test cluster to the possible Ganeti locations (`T286206`_).
* mysql_legacy: re-add ``x2`` database section and add support for active/active core sections (`T285519`_).

  * ``get_core_dbs()`` now supports excluding sections from its cumin query. All of the functions that call it in
    the context of setting the database read-only or read-write will now exclude sections listed in
    ``ACTIVE_ACTIVE_SECTIONS``.

Bug fixes
"""""""""

* puppet: when regenerating the client certificate, do not rely on the exit code of the Puppet command as it might be
  misleading. It already relies on successfully finding the certificate fingerprint.

Miscellanea
"""""""""""

* tox: remove ``flake8-import-order`` plugin as dependency now that the import order is ensured by ``black`` and
  ``isort``.

`v0.0.56`_ (2021-06-26)
^^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* mediawiki: reverted the change of v0.0.55 to make siteinfo API request over HTTPS.
* mediawiki: remove unnecessary and broken disable of systemd timers added in version v0.0.55.
* mysql_legacy: reverted the change of v0.0.49 to add the new ``x2`` database core section (`T285519`_).

`v0.0.55`_ (2021-06-24)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* mediawiki: Update cronjob code now that most are systemd timers.

  * Removed ``check_cronjobs_enabled()``.
  * Renamed ``stop_cronjobs()`` to ``stop_periodic_jobs()``.
  * Added ``check_periodic_jobs_disabled()``, ``check_periodic_jobs_enabled()`` and
    ``check_systemd_timers_enabled()``.

Bug fixes
"""""""""

* mediawiki: Make siteinfo API request over HTTPS.

`v0.0.54`_ (2021-06-21)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* icinga: rename some ``IcingaHosts`` methods:

  * This is an API breaking change, but the newly introduced ``IcingaHosts`` API is not yet used widely, just one
    Cookbook uses it so far.
  * Rename some methods of the ``IcingaHosts`` class to be more dry and explicit. Namely:
    * ``hosts_downtimed`` -> ``downtimed`` (context manager)
    * ``downtime_hosts`` -> ``downtime``
    * ``host_command`` -> ``run_icinga_command``

`v0.0.53`_ (2021-06-10)
^^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* icinga: use bash wrapper to allow sudo in the ``IcingaHosts`` class.

Miscellanea
"""""""""""

* doc: use ``add_css_file()`` instead of ``add_stylesheet()``.
* doc: fix parameter type in docstring.

`v0.0.52`_ (2021-05-06)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* dhcp: Add module for manipulating dynamic DHCP entries on target data centers and restarting the DHCP server
  (`T269855`_).
* icinga: pass ``verbatim_hosts`` option to the ``icinga-status`` script when using verbatim Icinga hostnames that
  are not real hosts.

Bug fixes
"""""""""

*  netbox: fix check for server role.

  * The physical devices and virtual machines objects in Netbox have different names for the role property
    (``device_role`` vs ``role``). Use the correct property each time.

* icinga: fix typo in docstring.

`v0.0.51`_ (2021-05-04)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* dnsdisc: do not configure DNS resolver. As the module is injecting the nameservers of the authoritative DNS, do not
  let the DNS module auto-configure itself with ``/etc/resolv.conf``.

Bug fixes
"""""""""

* tests: fix mock of the DNS module that was not in some cases properly mocked and the tests were relying on a properly
  configured ``/etc/resolv.conf``.

`v0.0.50`_ (2021-05-04)
^^^^^^^^^^^^^^^^^^^^^^^

Dependencies breaking changes
"""""""""""""""""""""""""""""

* setup.py: relax elasticsearch dependencies:

  * In order to be able to build spicerack for Debian bullseye that ships ``python3-elasticsearch`` ``7.1.0`` and
    ``python3-elasticsearch-curator`` ``5.8.1``, relax the related dependency constraints in ``setup.py``.
  * Elasticsearch requires to bump the version above the suggested compatibility matrix, we'll test if all works as
    expected. See the `elasticsearch compatibility matrix`_.
  * Elasticsearch curator matches upstream compatibility matrix, see the `elasticsearch curator compatibility matrix`.
  * As Spicerack is released via debian packages this will not affect the buster builds.

API breaking changes
""""""""""""""""""""

* netbox: improve ``as_dict()``:

  * Instead of calling ``serialize()`` for the conversion to dictionary, just calling ``dict()`` on the object gives a
    more useful representation of the object because all the nested properties are converted to string or
    sub-dictionaries with useful values instead of just the IDs.
  * As a result any usage of ``as_dict()`` that relied on the format of specific fields might break. At the moment no
    cookbook is using it.
  * See also the "Casting the object as a dictionary" example in `pynetbox.core.response.Record`_.

New features
""""""""""""

* netbox: add ``NetboxServer`` class:

  * Add a ``NetboxServer`` class in the netbox module to give a higher level abstraction across physical servers and
    virtual machines.
  * This is particularly useful to finally have an authoritative way to convert a hostname into a FQDN or get the
    managment FQDN of a host given its hostname (`T240176`_).
  * The class also allow to update the device status only if it's a physical host and the status transition is approved.
  * Those new features will be used by the cookbook that will replace the reimage script and then the current usage of
    some of the existing methods in the ``Netbox`` class should be converted to use this class instead.

* icinga: add new ``IcingaHosts`` class (`T277740`_):

  * Implements the TODO that wanted to move the ``Icinga`` class into a class that is initialized with the target hosts
    so that it's not necessary anymore to pass them to each method.
  * Keep the existing ``Icinga`` class for now, but mark it as deprecated, both in the documentation of
    ``spicerack.Spicerack.icinga()`` and ``icinga.Icinga()`` and emit also a ``DeprecationWarning`` when instantiated.
    It will be removed in the next release once all the cookbooks have been migrated to the new
    ``spicerack.Spicerack.icinga_hosts()`` accessor.
  * Move the detection of the Icinga command file to its own class to allow to cache it across different instances,
    making the instantiation of multiple ``IcingaHosts`` class free after the first one.
  * Allow to manage also non-servers that are defined as Icinga hosts passing the ``verbatim_hosts`` parameter, that
    will not extract the hostname from the given hosts assuming that they are already FQDNs.

* toolforge.etcdctl: Allow getting the cluster health. This opens up being able to wait/stop if the cluster status is
  not what's expected when doing operations (`T276338`_).

Minor improvements
""""""""""""""""""

* icinga: use a bash command wrapper to allow sudo, otherwise the echo command will fail to output to the file.
* icinga: use a sudo-friendly command to detect the Icinga ``command_file``.
* netbox: improve ``as_dict()``:

  * Instead of calling ``serialize()`` for the conversion to dictionary, just calling ``dict()`` on the object gives a
    more useful representation of the object because all the nested properties are converted to string or
    sub-dictionaries with useful values instead of just the IDs.
  * See also the "Casting the object as a dictionary" example in `pynetbox.core.response.Record`_.

Bug fixes
"""""""""

* remote: fix ``use_sudo`` on ``split()``.
* netbox: fix object type returned for status. The status should be returned as string and not as a Netbox object.
* doc: add documentation for the toolforge package.
* doc: remove obsolete configuration
* setup.py: add missing tag for Python 3.9, already supported.
* tests: fix pip backtracking separating the prospector tests into its own virtualenv.
* tests: fix format checking

  * If no Python files were modified at all, the latest isort would bail out. Skipping the checks if no Python files
    were modified at all.

* doc: fix documentation checker for sub-packages

  * The existing checker was assuming a flat space of modules inside spicerack, while now we have also subpackages.
    Adapt the checker to detect those too.
  * Convert file operations to pathlib.

Miscellanea
"""""""""""

* doc: move ClusterShell URL to HTTPS
* netbox: refactor unit tests

`v0.0.49`_ (2021-03-04)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* icinga: changed the type for the ``hosts`` parameter in the ``get_status()`` method from
  ``spicerack.typing.TypeHosts`` to ``cumin.NodeSet``.

New features
""""""""""""

* icinga: add ``Icinga.wait_for_optimal()`` method to pause while hosts converge to an optimal state.
* puppet: add ``Puppet.get_ca_servers()`` method to retrieve the configured Puppet ``ca_server`` on the target hosts.
* remote: allow prepending every command to execute on the target hosts with sudo. This is a first temporary iteration
  until Cumin will support it natively.
* toolforge.etcdctl: add new toolforge package with an etcdctl module to run etcdctl commands and retrieve a parsed
  output. Focused on etcd member management only for now (`T267412`_).

Minor improvements
""""""""""""""""""

* config: allow to use paths relative to the user's ``$HOME`` directory expanding ``~``.
* logging: improve logging format

  * Add the ``DRY-RUN`` prefix also to file logs to allow to distinguish dry-run executions from the real ones just
    looking at the logs.
  * Improve the execute cookbook log message including the whole arguments so that it includes also the global args
    such as ``verbose`` and ``dry-run``.

* remote: ``RemoteHosts.wait_reboot_since()`` is now using a constant backoff. Previously, a linear backoff with a base
  delay of 10 seconds was used. Since we do expect the reboot of a server to take some time, by the time the server has
  rebooted, the retry interval has already grown to multiple minutes. A constant backoff should be appropriate
  and should increase the reactivity of this check significantly.
* mysql_legacy.py: Add the new ``x2`` database core section (`T269324`_).

Bug fixes
"""""""""

* cookbooks: force the title to be one line. When reading the title from the cookbooks, pick only the first line to
  prevent the UI to be cluttered by a title erroneously set to multi-line.
* tox: fix for when the system setuptools is too old.
* elasticsearch: Revert the return the cluster name in ``ElasticsearchCluster.__str__`` change added in ``v0.0.32``.
* remote: fix pylint typing confusion.

Miscellanea
"""""""""""

* gitignore: add vim swap files.
* tests: temporary force ``mypy`` upper version to avoid a regression in release 0.800.
* tests: tox, enable python 3.9 support.
* code style: introduced ``black`` and ``isort`` as autoformatters (`T211750`_).
* documentation: add a development page to highlight how the code is formatted and how to integrate the code formatters
  with an editor/IDE or in the git workflow (`T211750`_).
* git: allow exclude code auto formatters refactor commit from git blame adding the ``.git-blame-ignore-revs`` file.

`v0.0.48`_ (2021-01-18)
^^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* logging: fix base path and name to setup logging.

  * In the recent refactor to the new APIs, the paths passed to the setup_logging function were not anymore correct.
    Now that the cookbook items have a proper Spicerack-formatted path and name, use them directly.

`v0.0.47`_ (2021-01-13)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* Use newly migrated code from wmflib:

  * Some additional functionalites were moved to wmflib (>= 0.0.5), remove the duplicated code from Spicerack and use
    the wmflib version instead.
  * interactive: convert all imports to use the wmflib version, remove the duplicated code. The module is for now left
    to hold the ``get_management_password()`` function.
  * prometheus: moved entirely to wmflib.
  * _log: use the SAL (!log) IRC handler from wmflib.
  * The ``@retry`` decorator will be migrated in a separate patch to keep its dry-run awareness.

Minor improvements
""""""""""""""""""

* administrative: Add getters for the other Reason fields.

Bug fixes
"""""""""

* puppet: update ``get_certificate_metadata()`` so the pattern is more specific and prevent it to match other hosts.
* elasticsearch_cluster: fix call to ``@retry``.

Miscellanea
"""""""""""

* dnsdisc: improve test coverage
* tests: fix deprecated pytest argument
* tox: Remove ``--skip B322`` from Bandit config not supported by newer Bandit versions.

`v0.0.46`_ (2020-12-10)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* icinga: add support for downtimed and notifications_enabled parameters (`T269672`_).
* elasticsearch-cluster: add support for cloudelastic (`T268779`_).

`v0.0.45`_ (2020-11-30)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* Removed config and phabricator modules migrated to wmflib and update imports.
* remote: re-enabled Cumin's output removing its suppression. The work on `T212783`_ will make it more flexible on
  a per-execution basis, but for now is better to just re-enable it and make the errors surface to the users.

New features
""""""""""""

* cookbook API: add class API

  * In addition to the simple cookbooks function API interface add support for a more integrated class-based API.
  * Spicerack will perform auto-detection of the API used by the cookbook and automatically convert the module-based
    API cookbooks into class-based cookbooks so that only one interface is actually supported internally.
  * The class API defines a ``CookbookBase`` class that cookbooks that want to use this API must extend creating a
    derived class. The derived class can have any name. Multiple cookbooks in the same module are supported.
  * The class-based API allows a more in-depth integration with Spicerack:

    * Allow to perform additional initialization and validation steps in the class constructor before the cookbook
      execution starts, allowing the cookbook to bail out before execution and any related ``!log-ging``.
    * Allow to define a custom runtime description that will be included, for example, in the ``START/END`` logging
      messages that are also sent to IRC and ``!log-ed`` into SAL.
    * Refactor the Cookbook API documentation to be more detailed and following Sphinx standards to document the
      cookbooks module interfaces.
    * Refactor out from the private ``_cookbook`` module some functionalities to a ``_menu`` and ``_module_api``
      modules.

* spicerack: add ``requests_session`` accessor to get a requests's ``Session`` pre-configured by ``wmflib`` with a
  default timeout, retry logic and ``User-Agent``.
* decorators: Add an optional custom failure message to ``@retry``:

  * The ``@retry`` decorator logs the messages from exceptions raised during execution, but when there are chained
    exceptions ("raise from", etc.) only the top-level error is logged. For example, in ``MediaWiki._check_siteinfo``,
    we only log ``Failed to get siteinfo`` and throw away the message from the underlying ``RequestException``.
    Instead, this traverses the exception chain (using the same logic as the built-in default handler for uncaught
    exceptions) and includes each exception's message in the log entry.

Minor improvements
""""""""""""""""""

* Convert all usage of the ``requests`` package to use the ``wmflib.requests.http_session`` instead to have a nice
  ``User-Agent``, a default timeout and a retry logic on some failures across ``Spicerack``.
* puppet: suppress deprecation warnings.
* decorators: Log chained exception messages in ``@retry``.

Miscellanea
"""""""""""

* doc: add missing link to the ``wmflib`` package.
* dependencies: remove temporary hacks.
* dependencies: update min version to match the versions in Debian Buster.
* tests: remove ``require_*`` decorators.
* Refactoring: renamed internal modules with a leading underscore:

  * Moved ``cookbook.py`` to ``_cookbook.py`` and ``log.py`` to ``_log.py`` as all their content is actually internal
    to ``spicerack`` and no client should use any of that. They were already excluded from the generated documentation
    for the same purpose.

`v0.0.44`_ (2020-10-13)
^^^^^^^^^^^^^^^^^^^^^^^

Breaking changes
""""""""""""""""

* dns: the ``dns`` module has been migrated to ``wmflib`` and removed from Spicerack. Its access via the
  ``spicerack.dns(()`` accessor is unchanged, but any direct imports from the ``spicerack.dns`` module in
  cookbooks must be replaced with ``wmflib.dns`` (`T257905`_).

Miscellanea
"""""""""""

* Spicerack now depends on the new ``wmflib`` package.
* log: adjust the return type of ``FilterOutCumin.filter()`` as required by mypy (upstream documentation incorrect).
* documentation: refactor and simplify its configuration.
* pylint: allow ``logger`` as module-scope name given that is used throughout the project so that there is no need for
  a pylint disable comment.

`v0.0.43`_ (2020-09-16)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* elasticsearch: Store which datacenters to query for metrics in Prometheus.

`v0.0.42`_ (2020-08-31)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch: fix prometheus query syntax.

`v0.0.41`_ (2020-08-31)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* dnsdisc: change retry logic to wait up to 27 seconds with more frequent checks instead of the current 9 seconds.

`v0.0.40`_ (2020-08-27)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* elasticsearch_cluster: verify all write queues are empty querying Prometheus (`T261239`_).

Miscellanea
"""""""""""

* doc: improved logging documentation.

`v0.0.39`_ (2020-08-18)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Add native mysql spicerack module.

Bug Fixes
"""""""""

* mysql_legacy: update Cumin queries for DB selection due to Puppet refactors.
* icinga: fix bug for ``recheck_all_services()``, the signature of the Icinga command requires a check time too.

Miscellanea
"""""""""""

* Remove support for Python 3.5 and 3.6.
* actions: refactored to take advantage of more recent Python versions.
* Add type hints for variables and attributes since the support for older Python versions has been dropped.
* Pin to a working version of prospector as 1.3.0 was overenthusiastic with updating its dependencies.
* actions: fix test for pytest regression in version 6.0.0.

`v0.0.38`_ (2020-06-09)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* ganeti: update the list of available rows in the ``eqiad`` and ``codfw`` datacenters.

Miscellanea
"""""""""""

* Add support for Python 3.8.

`v0.0.37`_ (2020-05-18)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* icinga: fix ``get_status()``:

  * The ``icinga-status`` script that returns the status can be run also in dry-run mode as it's a read-only tool.
  * The ``icinga-status`` script exits with a non-zero exit status on non-optimal and missing hosts, accept any exit
    code.

`v0.0.36`_ (2020-05-18)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* tests: add ``@require_caplog`` to some ``actions`` module tests to fix the build on Debian Stretch.

`v0.0.35`_ (2020-05-18)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* Rename ``mysql`` module to ``mysql_legacy``:

  * The existing ``mysql`` module uses remote execution of the mysql client to interact with mysqld's. Moving this out
    of the way to allow room for a new ``mysql`` module which uses a native mysql client library.

New features
""""""""""""

* interactive: add ``get_secret()`` function for requesting secrets interactively with optional ask for confirmation.

* icinga: allow to check the status of a host:

  * Add a ``get_status()`` method that allows to get the current status of a set of hosts in Icinga.
  * The returned status allow to quickly check if all the hosts are in optimal state, get a list of those that are not
    and the services that are failing on those hosts.

* actions: new module to track cookbook actions:

  * Add a new actions module that contains an ``Actions`` class and an ``ActionsDict`` class that is an ordered
    dictionary with default dictionary functionalities of ``Actions`` class instances.
  * The ``Actions`` instances allow to keep track of actions performed by acookbook with the following features:

    * Save the message of the action with different levels (``success``, ``warning``, ``failure``).
    * Log the message of the action with the associated log level.
    * Keep track of the presence of any warning or failure.
    * Have a nice string representation of the actions, suitable to be used to update a Phabricator task.

  * The ``ActionsDict`` class has too a nice string representation of its items.
  * This is a porting with some generalization of the code present in the `sre.hosts.decommission`_ cookbook.
  * Pre-create an ``ActionsDict`` instance in spicerack so that it can be accessed in the cookbooks directly as
    ``spicerack.actions``.

* typing: add a ``typing`` module for custom type hints:

  * Add a new typing module to hold all custom types useful across Spicerack.
  * Define a custom type ``TypeHosts`` that can be either a ``NodeSet`` or a sequence of strings.
  * Use the new type in the icinga module.

Bug Fixes
"""""""""

* ipmi: fix ``subprocess.run()`` calls to raise on failure.

  * The ``check`` parameter is by default :py:data:`False`, hence not raising an exception if the executed command exit
    with a non-zero exit code.
  * Forcing the ``check`` parameter to be :py:data:`True` to ensure an exception is raised on failure.

Miscellanea
"""""""""""

* icinga: refactor input parsing:

  * The Icinga class needs to use hostnames instead of FQDNs.
  * Move the conversion from FQDNs (or hostnames) to hostnames to a static method so that can be used across the
    class without repetition of code.

* tests: fix newly reported flake8 issues.
* tests: relax Prospector dependency

  * The upstream bug that required to set an upper limit on the version of Prospector has been fixed.
  * Removing the upper bound to get newer features.
  * Fix newly reported issues.

* tests: relax Bandit dependency

  * The upstream bug that required to set an upper limit on the version of Bandit has now a workaround using a specific
    syntax for the exclude files.
  * Removing the upper bound to get newer features.
  * Fix newly reported issues.
  * Remove ``nosec`` comments not needed anymore and convert some of them into skipped checks in ``tox.ini``. This way
    the affected lines are still checked for other issues.

`v0.0.34`_ (2020-05-06)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* netbox: removed property ``device_status_choices`` of the ``Netbox`` class, not currently used and removed from Netbox
  API starting from version 2.8.0.

Bug Fixes
"""""""""

* netbox: adapt to new Netbox API:

  * Netbox API starting with Netbox 2.8.0 have removed the choices API endpoint. Given that it was used only for the
    status, removing its support completely for now given that is not directly supported by the pynetbox library yet.

Miscellanea
"""""""""""

* doc: set min version of sphinx_rtd_theme to 0.1.9 to match Debian Stetch.
* doc: fix documentation generation for Sphinx 3
* changelog: specify breaking change for v0.0.33.

`v0.0.33`_ (2020-05-04)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* netbox: the default instance returned when calling ``Spicerack.netbox()`` uses a read-only token. To have read-write
  access to Netbox the ``read_write`` parameter should be set to ``True``.

New features
""""""""""""

* netbox: add support for RW and RO tokens:

  * Use a RO token by default, allow to request a Netbox instance with a RW token.
  * Always use a RO token if in dry-run mode to allow to expose the Netbox API object directly to the clients.

* netbox: expose the pynetbox API object:

  * To allow to perform additional operations not yet abstracted by the Netbox class, expose the pynetbox API object
    directly.
  * The dry-run mode support is ensured by the RO token.

Minor improvements
""""""""""""""""""

* include the username in logfiles

`v0.0.32`_ (2020-03-11)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* spicerack: allow to override Spicerack's instance parameters from the configuration file. See :ref:`config.yaml`.
* spicerack: allow to cache the ``Ipmi`` instance so that it can be re-used without re-asking the management password.
* spicerack: expose to cookbooks the ``_spicerack_config_dir`` parameter via a getter.
* netbox: fine tune log and exception messages.
* elasticsearch: return the cluster name in ``ElasticsearchCluster.__str__``.
* mysql: update ``CORE_SECTIONS`` for external storage RW instances (`T226704`_).

Bug Fixes
"""""""""

* elasticsearch: add ``https://`` to relforge endpoints.

Miscellanea
"""""""""""

* tests: remove unused mypy type ignore comments.

`v0.0.31`_ (2020-02-26)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* ganeti: add VM creation capability (`T231068`_).
* spicerack: add support for an HTTP proxy.

  * To perform calls to external endpoints it might be necessary to use an HTTP proxy, add support for it.
  * Read the ``http_proxy`` config from the main spicerack configuration file and inject it into Spicerack that will
    also expose it to the cookbooks.
  * Add a getter for the ``http_proxy`` property to Spicerack.
  * Add a helper that returns a ``proxies`` dictionary to be used by the Python Requests module.

Minor improvements
""""""""""""""""""

* ganeti: use canonical Ganeti cluster names (`T231068`_).
* ganeti: add logging for ``GntInstance`` actions (`T231068`_).


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
.. _`sre.hosts.decommission`: https://gerrit.wikimedia.org/r/plugins/gitiles/operations/cookbooks/+/cea161a91ec21dcd48fe0d3fa899c1f19fc4801b/cookbooks/sre/hosts/decommission.py#42
.. _`pynetbox.core.response.Record`: https://pynetbox.readthedocs.io/en/latest/response.html#pynetbox.core.response.Record
.. _`elasticsearch compatibility matrix`: https://elasticsearch-py.readthedocs.io/en/stable/#compatibility
.. _`elasticsearch curator compatibility matrix`: https://www.elastic.co/guide/en/elasticsearch/client/curator/current/version-compatibility.html

.. _`T147074`: https://phabricator.wikimedia.org/T147074
.. _`T211750`: https://phabricator.wikimedia.org/T211750
.. _`T212783`: https://phabricator.wikimedia.org/T212783
.. _`T213296`: https://phabricator.wikimedia.org/T213296
.. _`T219640`: https://phabricator.wikimedia.org/T213296
.. _`T219799`: https://phabricator.wikimedia.org/T219799
.. _`T226704`: https://phabricator.wikimedia.org/T226704
.. _`T229792`: https://phabricator.wikimedia.org/T229792
.. _`T231068`: https://phabricator.wikimedia.org/T231068
.. _`T240176`: https://phabricator.wikimedia.org/T240176
.. _`T243935`: https://phabricator.wikimedia.org/T243935
.. _`T257905`: https://phabricator.wikimedia.org/T257905
.. _`T261239`: https://phabricator.wikimedia.org/T261239
.. _`T267412`: https://phabricator.wikimedia.org/T267412
.. _`T268779`: https://phabricator.wikimedia.org/T268779
.. _`T269324`: https://phabricator.wikimedia.org/T269324
.. _`T269672`: https://phabricator.wikimedia.org/T269672
.. _`T269855`: https://phabricator.wikimedia.org/T269855
.. _`T276338`: https://phabricator.wikimedia.org/T276338
.. _`T277740`: https://phabricator.wikimedia.org/T277740
.. _`T285519`: https://phabricator.wikimedia.org/T285519
.. _`T285706`: https://phabricator.wikimedia.org/T285706
.. _`T285803`: https://phabricator.wikimedia.org/T285803
.. _`T285804`: https://phabricator.wikimedia.org/T285804
.. _`T286206`: https://phabricator.wikimedia.org/T286206
.. _`T288558`: https://phabricator.wikimedia.org/T288558
.. _`T289078`: https://phabricator.wikimedia.org/T289078
.. _`T291681`: https://phabricator.wikimedia.org/T291681
.. _`T299123`: https://phabricator.wikimedia.org/T299123

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
.. _`v0.0.31`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.31
.. _`v0.0.32`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.32
.. _`v0.0.33`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.33
.. _`v0.0.34`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.34
.. _`v0.0.35`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.35
.. _`v0.0.36`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.36
.. _`v0.0.37`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.37
.. _`v0.0.38`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.38
.. _`v0.0.39`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.39
.. _`v0.0.40`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.40
.. _`v0.0.41`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.41
.. _`v0.0.42`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.42
.. _`v0.0.43`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.43
.. _`v0.0.44`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.44
.. _`v0.0.45`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.45
.. _`v0.0.46`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.46
.. _`v0.0.47`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.47
.. _`v0.0.48`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.48
.. _`v0.0.49`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.49
.. _`v0.0.50`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.50
.. _`v0.0.51`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.51
.. _`v0.0.52`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.52
.. _`v0.0.53`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.53
.. _`v0.0.54`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.54
.. _`v0.0.55`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.55
.. _`v0.0.56`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.56
.. _`v0.0.57`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.57
.. _`v0.0.58`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.58
.. _`v0.0.59`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v0.0.59
.. _`v1.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.0
.. _`v1.0.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.1
.. _`v1.0.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.2
.. _`v1.0.3`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.3
.. _`v1.0.4`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.4
.. _`v1.0.5`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.5
.. _`v1.0.6`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.0.6
.. _`v1.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.1.0
.. _`v1.1.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v1.1.1
.. _`v2.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.0.0
