Spicerack Changelog
-------------------

`v11.3.0`_ (2025-07-09)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* dhcp: add a config to match based on the host UUID, sent in Option 97, pxe-client-id, rather than the MAC or
  Option 82 info.
* redfish: add support for iDRAC 10 to ``force_http_boot_once``.
* netbox: expose the switches a server is connected to.
* cookbook API: simplify ``-t/--task-id`` support:

  * Use directly the wmflib's Phabricator task validator as type in the argument parser instance. When the argument
    is not mandatory set a default value of empty string that will make all the calls to the Phabricator's instance
    noop.
  * Set ``allow_empty_identifiers`` to ``True`` when instantiating a Phabricator instance to allow the calls to
    Phabricator to be noop when using an empty identifier.
  * This will allow to simplify a lot of logic in the cookbooks that will be able to blindly call the phabricator
    methods and decide if they should raise or not on failure.

* administrative: add support for empty task ID. Don't include the task ID in the reason message if it's an empty
  string. Add this support so that when using the newer wmflib's Phabricator capabilities if empty string is used
  it will be supported in this module too.

Bug fixes
"""""""""

* icinga: fix mypy call-overload reported error.

Miscellanea
"""""""""""

* tox: add python 3.12 and 3.13, skip Python 3.10 in CI.
* redfish: add some more tests.

`v11.2.0`_ (2025-06-26)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* dhcp: add support for vendor exclusion to the ``DHCPConfMac`` class like the ``DHCPConfOpt82`` one.

Bug fixes
"""""""""

redfish: fix support for SCP on iDRAC 10 that was not properly added in the previous release.

`v11.1.0`_ (2025-06-25)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* redfish: add ``get_primary_mac()`` method to gather the MAC address of the interface on which PXE is enabled.
* netbox: add ``primary_mac_address()`` getter and setter to the ``NetboxServer`` class to manipulate interface MAC
  addresses.

Bug fixes
"""""""""

* redfish: add support for iDRAC 10. It requires the specification of an additional parameter for the SCP
  functionalities. Add it only when an iDRAC 10 is detected.

Miscellanea
"""""""""""

* locking: fix unit test missing assert

`v11.0.0`_ (2025-05-28)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* ganeti: when creating new VMs make the storage type configurable. It breaks compatibility for the
  ``spicerack.ganeti.GntInstance.add()`` method.

Minor improvements
""""""""""""""""""

* icinga: allow to skip downtimed services in ``wait_for_optimal()``.

Miscellanea
"""""""""""

* .wmfconfig: build spicerack also for Debian Bookworm.

`v10.2.0`_ (2025-05-07)
^^^^^^^^^^^^^^^^^^^^^^^

Temporary API breaking changes
""""""""""""""""""""""""""""""

* elasticsearch: temporarily remove support for elasticsearch on Debian Bookworm and Python versions 3.10+.
  As the current version of the elasticsearch module in not compatible with the upstream newer versions of the
  elasticsearch libraries, temporarily removing its support from spicerack when on newer versions of Debian or
  Python. Accessing the ``elasticsearch_cluster()`` Spicerack accessor on Debian Bookworm if installed via deb
  package or Python 3.10+ if installed via pip will raise an exception. On Debian Bullseye (deb) and Python 3.9 (pip)
  nothing changes (`T390860`_).

Bug fixes
"""""""""

* k8s: to support future upgrades allow both ``V1beta1Eviction`` and ``V1Eviction`` imports from the kubernetes module.

Miscellanea
"""""""""""

* setup.py: update kubernetes and redis dependencies to support also bookworm.
* doc: expand logging documentation.

`v10.1.0`_ (2025-04-15)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* hosts: add a new ``hosts`` module with a ``Host`` class:

  * The ``Host`` class is meant to represent a single host and expose a bunch of services already available via
    Spicerack directly for this single host.
  * It gets initialized via a hostname string and it ensures the host exists in Netbox and, when using the
    ``host.remote()`` accessor, also in PuppetDB.
  * Move some ``Netbox`` pytest fixtures to ``conftest.py`` so that they can be used also in the ``Host`` tests.

Minor improvements
""""""""""""""""""

* remote: make ``RemoteHosts`` iterable, returning a new ``RemoteHosts`` instance with just one host for each host in
  the original instance.
* mysql: make ``MysqlRemoteHosts`` iterable, returning a new ``MysqlRemoteHosts`` instance with just one host for
  each host in the original instance.
* mysql: add a ``split()`` method similarly to the one present in ``RemoteHosts``.
* cookbook modules: use docstring for title if ``__title__`` is not set as in most cases the ``__title__`` property
  of the cookbooks using the module API and the cookbooks packages (``__init__.py`` files) set it to be the docstring
  of the module (e.g. ``__title__ = __doc__``).
* cookbook: improve the ``-r/--reason`` help message autogenerated by ``CookbookBase`` when
  ``argument_reason_required`` is set.
* logging: automatically rotate log files:

  * Make the cookbook logging files rotating with a maximum of 10MB each for both the standard and extended logging.
  * Trying to keep logs forever for auditing purposes, set the max files to 500.
  * In the extended logs, instead of the filename of the line log source, use the logger name, that might be more
    representative for external libraries.

* log: notify the user on IRC when there is a cookbook waiting for input:

  * Configure the wmflib's notification logger defined in ``wmflib.interactive.notify_logger`` so that it will send
    a message on IRC to the user running the cookbook.
  * The message will have ``username@host`` already and we're providing the last part of the name of the cookbook
    (e.g. ``reimage`` for the ``sre.hosts.reimage`` cookbook) and the process ID that is awaiting user input.
  * The message will be sent to the ``#wikipedia-operation`` channel for now, but if ircecho is improved this mechanism
    could also send private messages instead.
  * The whole feature is behind feature flag configuration key to enable/disable it.

Bug fixes
"""""""""

* dnsdisc: make the module compatible with bookworm's version of dnspython.
* tests: refactor logging related tests to ensure that the reset of the logging module is done in any case,
  preventing false positive failures in case of another test failing and not properly resetting the logging module.

Miscellanea
"""""""""""

* doc: fine-tune settings for magic methods:

  * Add ``__iter__``, ``__len__`` and ``__str__`` to the list of magic methods for which documentation should always
    be created.
  * Remove the specific setting from the modules that had that individually.
  * Improve the docstrings for those methods to better explain what they are returning/doing.

`v10.0.0`_ (2025-03-31)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* constants: replaced ``PUPPET_CA_PATH`` to ``WMF_CA_BUNDLE_PATH``, no cookbook is directly importing it.
* spicerack: convert some ``@property`` into methods:

  * To be more friendly with the upcoming spicerack-shell, convert some ``@property``, that will
    generates either output or request input when using autocompletion, to methods to prevent them to be executed
    when using autocompletion in the spicerack-shell.
  * API breaking change: this will require to change the few direct use of those properties in the cookbooks
    repository. Given the very limited usage it seems overkill to do this change in a backward compatible way as it
    will be very easy to do a coordinated deploy.
  * Changed properties:

    * ``icinga_master_host`` became ``icinga_master_host()``.
    * ``netbox_master_host`` became ``netbox_master_host()``.
    * ``management_password`` became ``management_password()``.

New features
""""""""""""

* cookbook: make the default argument parser tunable:

  * Adds two class properties to the ``spicerack.cookbook.CookbookBase`` class to allow to tune the automatical
    injection of common command line arguments that many cookbooks add by themselves.
  * ``argument_reason_required`` allows to inject a ``-r/--reason`` argument.
  * ``argument_task_required`` allows to inject a ``-t/--task-id`` argument.
  * The arguments can be added as required or not based on the value of the class attribute:

    * ``None``: do not include the argument, default.
    * ``False``: include the argument but set it as non required.
    * ``True``: include the argument and set it as required.

Minor improvements
""""""""""""""""""

* constants: replace path of the old Puppet CA:

  * Replace the path to the old Puppet CA certificate with the newer WMF bundled of certificates that includes both
    the new PKI CA and the old Puppet CA.
  * Replace the constant name from ``PUPPET_CA_PATH`` to ``WMF_CA_BUNDLE_PATH``, no cookbook is directly importing it.
    This is an API breaking change.
  * This way its usage will be forward and backward compatible, allowing clients to connect independently if the
    server has switched to the new PKI-based certificates or not.

* redfish: wait few seconds in ``scp_dump()`` before starting polling the job results so that if the job is quick
  (like when collecting only one sets of items) it can complete before the first attempt avoiding to wait for 30s.

Bug fixes
"""""""""

* puppet: remove spurious spaces from ``run()`` command.
* setup.py: limit ``kafka-python`` version to ``2.0.*``, the recently released ``2.1.0`` has some backward
  incompatible changes.

Miscellanea
"""""""""""

* tests: remove unnecessary vulture settings, newer Vulture don't detect those as false positive anymore.
* setup.py: update prospector pin to the latest version.

`v9.1.3`_ (2025-02-25)
^^^^^^^^^^^^^^^^^^^^^^

Miscellanea
"""""""""""

* setup.py: revert conftool dependency extra requirement `with-dbctl` to decouple the release of both softwares.

`v9.1.2`_ (2025-02-25)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* spicerack: extend the ``run_cookbook()`` accessor with two new optional parameters:

  * ``raises``: make the call raise a new ``spicerack.exceptions.RunCookbookError`` exception if the execution
    returns non-zero exit code.
  * ``confirm``: wrap the call with a ``confirm_on_failure()`` call.

* spicerack: allow to refresh the service catalog from disk adding a ``refresh`` argument to the ``service_catalog()``
  accessor.
* dbctl: pass a ``DbCtlConfiguration`` instance to ``DbConfig`` to complete the migration to the new API.

Miscellanea
"""""""""""

* setup.py: add with-dbctl extra to conftool dependency to be future-proof.

`v9.1.1`_ (2025-01-28)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* service: Add ``scheduler_flag`` field to ``ServiceLVS`` to be in sync with the same addition in Puppet's repo.

`v9.1.0`_ (2025-01-15)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* cookbook API: add ``owner_team`` property (`T379258`_):

  * Add an ``owner_team`` property to the cookbook ``CookbookBase`` class API. It defaults to ``"unowned"``.
  * Add an ``__owner_team__`` module variable to the cookbook deprecated module API. It defaults to ``"unowned"``.
  * When ``__owner_team__`` is set on an ``__init__.py`` file for a cookbook package (directory of cookbooks) it will
    apply the ownership to all cookbooks in that package unless they override the ownership themselves.
  * Use the new property in the cookbook listing with or without the verbose option to show the owner of the cookbook
    in square brackets.
  * Inject the cookbook owner in the help message to the parser epilog.

* api: allow to abort a cookbook execution before ``run()`` is called (`T365454`_):

  * If a cookbook raises a ``cookbook.CookbookInitSuccess`` exception in its runner's ``__init__()``, Spicerack will
    consider the execution successful, will not print any stack trace and the exit code will be ``0``.
  * This allows to run the cookbook in report/read-only mode in ``__init__()`` and exit successfully without ever
    running ``run()`` and also without logging to SAL.

* api: allow to skip the ``START`` log to SAL (`T324655`_):

  * Add a ``skip_start_sal`` property to the ``CookbookRunnerBase`` class that defaults to ``False`` to allow to skip
    the START log to SAL.
  * This is meant to be used by fast cookbooks that take a short time and for which there is no need for the double
    logging of ``START`` and ``END``.
  * When set to ``True`` Spicerack will log the ``START`` line only in the console and the log files but not IRC/SAL.
    It will also change the word ``END`` for the log at the end of the cookbook in ``DONE``.
  * This means that normal cookbooks will log:
        * ``START - ...``
        * ``END (pass) - ...``
    while cookbooks that set ``skip_start_sal`` to ``True`` will just log:
        * ``DONE (pass) - ...``
  * The property can be set dynamically by the cookbook class, so that the same cookbook can be logged in different
    ways based on the CLI arguments that might cause the cookbook to be fast or slow.

Bug fixes
"""""""""

* netbox: support Ganeti setup when looking for the VLAN a host's primary address is part of. This add support to cases
  where the primary IP is on a bridge interface and will automatically get the VLAN of the physical interface the
  bridge is part of.

Miscellanea
"""""""""""

* style: a pass of black on all files to apply more recent black modification to the whole code base at once.
* style: enum: remove type hints for ``Enum`` classes to follow most recent standards.

`v9.0.0`_ (2024-12-02)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* mysql_legacy: rename to ``mysql`` and remove ``Legacy`` from all the class names. This replaces the unused old
  ``mysql`` module whose functionality has been moved to ``mysql.MysqlClient``
* mysql: make ``fetch_one_row()`` return always a dict also in case of no rows matching to simplify client's code and
  mypy checks.

`v8.16.2`_ (2024-11-18)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* redfish: add response logging for request() to better capture errors that are hard to reproduce.

Bug fixes
"""""""""

* mysql_legacy: improve DRY-RUN support in execute() and documentation for it on the other methods.

`v8.16.1`_ (2024-11-14)
^^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* mysql_legacy: fix `set_master_use_gtid()` query, its value it's part of the syntax, avoid pymysql quoting it.
* mysql_legacy: fix query formatting in `set_replication_parameters()`.
* mysql_legacy: fix check in `replication_lag()` that would raise if the lag is 0.0s.
* doc: fix example code bug missing a reference to ``self``.

`v8.16.0`_ (2024-11-13)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* mysql_legacy: add ``MysqlClient`` class as a copy of the ``mysql.Mysql`` class to later merge those two modules
  together.
* mysql_legacy: improve pymysql usability adding some new helper methods:

  * ``execute()``: to execute a query that doesn't return anything via pymysql.
  * ``fetch_one_row()``: to execute a query with pymysql that should return one row and return it.
  * ``check_warnings()``: to check if in the last statement there was any warning raised and ask the user what to do.

* mysql_legacy: in the ``Instance`` class convert all internal queries to use the new methods to use pymysql instead of 
  executing queries via ssh.

Bug fixes
"""""""""

* mysql: remove deprecated call to ``query()`` method of pymysql that is for internal use only. Convert it to a
  ``cursor().execute()`` call that is the part of the public facing API.

`v8.15.2`_ (2024-10-31)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* elasticsearch: removed ``ElasticsearchHosts.get_remote_hosts()`` getter, superseded by the new
  ``RemoteHostsAdapter.remote_hosts()``.
* puppet: removed ``PuppetServer.server_host()`` and ``PuppetMaster.master_host()`` getters, superseeded by the new
  ``RemoteHostsAdapter.remote_hosts()``.
* Because of the very low usage of the above methods this didn't warrant a major release. Reporting it as breaking
  here for completeness, their usage will be fixed right after releasing this version.

Minor improvements
""""""""""""""""""

* remote: add ``remote_hosts`` getter to the ``RemoteHostsAdapter`` to ease the use from clients. This also removes
  one-off getter from other classes in the ``puppet`` and ``elasticsearch_cluster`` modules.

Bug fixes
"""""""""

* orchestrator: do not retry on 500s as orchestrator tends to reply to non-existing objects with a 500 with a JSON
  response, do not retry the request.
* mysql_legacy: accept any exit code for systemctl status to prevent having ``RemoteExecutionError`` exceptions.
* mysql_legacy: add getter for the ``Instance``'s ``socket`` property.
* mysql_legacy: fix ``list_host_instances()`` detection of single and multi-instances independently of the status of
  the systemd unit.

`v8.15.1`_ (2024-10-23)
^^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* orchestrator: fix bug with older requests that doesn't have the ``JSONDecodeError`` exception.
* service: change ``depool_threshold`` field to float following Puppet related change.

`v8.15.0`_ (2024-10-23)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* mysql: refactor this currently unused module to be up to date with the current infrastructure while simplifying it.
  Because of the unused nature of the module this didn't warrant a major release. Reporting it as breaking here for
  completeness.

New features
""""""""""""

* orchestrator: add a new module to interact with Orchestrator's APIs.
* apiclient: add a generic API client module and related Spicerack accessor.

Minor improvements
""""""""""""""""""

* redfish: use the new apiclient module.
* redfish: add UEFI functions to check if a host is setup with UEFI and to boot into UEFI HTTP.
* puppet: add format option to ``hiera_lookup``.
* mysql_legacy: add data directory accessor.
* mysql_legacy: re-order the ``CORE_SECTIONS`` constant from the less impactful to most impactful.
* mysql_legacy: get systemd status for instance to easily check if the instance is running or not.
* mysql_legacy: add ``cursor`` method to the ``Instance`` class to get a mysql client connection to the instance.
* remote: add ``dry_run`` getter for ``RemoteHosts``, useful for ``RemoteHostsAdapter`` implementations.

Bug fixes
"""""""""

* dhcp: Add option to omit sending filename to a vendor, used for the Debian Installer.

Miscellanea
"""""""""""

* doc: removed deprecated call to ``sphinx_rtd_theme``.
* tox: only install flake8 when running flake8.
* tests: fix issues reported by pylint >3 and pin Prospector.

`v8.14.0`_ (2024-09-30)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* dbctl: add new module to interact with dbctl (`T362893`_).

  * Add a new spicerack accessor to get a ``Dbctl`` instance.
  * From the ``Dbctl`` instance allow to access the dbctl libraries for ``Instance``, ``Section`` and ``DbConfig``
    (mediawiki config).
  * Dry-run support is ensured via the parent ``Confctl`` class that sets the ``read_only`` argument to the
    ``ConftoolClient`` instance accordingly.

Minor improvements
""""""""""""""""""

* confctl: add native support for RO in conftool

  * The spicerack interface to Conftool via the ``ConftoolEntity`` class does honor dry-run itself, although conftool
    was not having a dry-run support.
  * With recent contool development we can now use ``ConftoolClient`` to initialize it and this interface allows to
    set a ``read_only`` parameter.
  * The ``ConftoolClient`` interface abstracts the setup of the conftool client from the caller, in place of the to-be
    deprecated ``kvobject.KVObject.setup`` method.
  * Use the ``read_only`` parameter when in dry-run mode, both for safety reasons and also to enable using more complex
    conftool operations, such as the ones offered by the dbconfig extension.

Miscellanea
"""""""""""

* netbox: removed Netbox 3 backward compatibility, all existing Netbox instances are 4+.

`v8.13.1`_ (2024-09-17)
^^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* mysql_legacy: Add a 1 second sleep after ``start_slave()`` to ensure that a subsequent call to
  ``show_slave_status()`` would be reliable. Rename ``master_use_gtid()`` to ``set_master_use_gtid()`` for better
  clarity of the RW nature of it.

`v8.13.0`_ (2024-09-06)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* doc: add intersphinx_timeout (`T367410`_).

  * The config should allow to have quicker Debian builds when
    the network is not available.

* redfish: allow 200 responses in chassis_reset (`T365372`_).

  * On Supermicro nodes, chassis_reset's HTTP call gets a HTTP 200
    from the BMC, not 204. It seems ok to relax the condition
    and allow both 204 and 200, without extra logging since
    the Supermicro's BMC response is not useful.

* redfish: catch no-json-responses in change_user_password (`T365372`_).

  * The Supermicro's Redfish implementation works the same as Dell's
    in change_user_password, except for the fact that no JSON response
    is returned.

* redfish: introduce the AccountManager URI for DELL (`T365372`_).

  * From various tests it seems that the /redfish/v1/AccountService
    URI works on DELL too, but only for "read-only", namely getting
    accounts' info. Refactor a bit the redfish class and the find_account()
    method to take this into account.


`v8.12.0`_ (2024-09-02)
^^^^^^^^^^^^^^^^^^^^^^^

Dependencies breaking changes
"""""""""""""""""""""""""""""

* setup.py: update pynetbox to 7.4 (`T373794`_).

  ** After T371890#10081172 Spicerack fails to build due to pynetbox,
     since it was upgraded to 7.4


`v8.11.0`_ (2024-09-02)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* dhcp: allow empty distro for DHCPConfMac and DHCPConfOpt82 (`T365372`_).

  * Allow "distro" to be empty, so that the correspondent pathprefix
    config is not rendered. This is useful when we want to add
    DHCP configs for IP configuration only, like the Supermicro
    BMC/mgmt interface.

Minor improvements
""""""""""""""""""

* tox: run less environments on CI (`T372485`_).


`v8.10.0`_ (2024-08-01)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* mysql_legacy: Instance class improvements (`T371351`_).

  * Rename `use_gtid()` to `master_use_gtid()` to follow MySQL naming
    convention. Change its signature to accept a setting parameter to
    pick which valid value to use.
  * Introduce a `MasterUseGTID` enum class to represent the valid values
    that can be used for the MASTER_USE_GTID parameter.
  * Add a `run_vertical_query()` method to run a query with the vertical
    output format (\G) and parse its result to a list of dictionaries.
  * Adapt the other methods that would benefit of the above method to
    use it.

* redfish: add the add_account function (`T365372`_).

  * Supermicro ships their servers with the BMC admin account set to
    `ADMIN`, meanwhile we standardized the usage of `root` inside Wikimedia
    (basically what Dell does by default).
    Added a new add_account function that uses Redfish to create a new account.


`v8.9.0`_ (2024-07-25)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* dhcp: add ``dhcp_filename`` and ``dhcp_options`` for DHCPConfMac and DHCPConfOpt82 (`T363576`_).

  * The DHCP configuration can now be customized with ad-hoc `filename` and
    DHCP `option` settings.


Bug fixes
"""""""""

* mysql_legacy: fix Instance's upgrade path (`T367496`_)

  * The binary that runs the mysql upgrade needs to run other tools within
    the same directory and when called with a full path it will try to run
    them from the same path. But because the mysql_upgrade binary has a
    chain of symlink, we need to resolve them first before being able to
    run it with the full path.

`v8.8.0`_ (2024-07-18)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* netbox: add support for Netbox 4 (`T336275`_).

  * Limited support for cables with multiple terminations per sides:
    the first termination is the only one considered.

Minor improvements
""""""""""""""""""

* netbox: refactor tests to be more flexible, and adapt them for Netbox 4.

`v8.7.0`_ (2024-07-16)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* redfish: add property for storage manager URI (`T365372`_):

  * Add a new property for ``RedfishDell`` and ``RedfishSupermicro``
    to be used as helper in various cookbook that require the URI
    path to get Storage Members info.

Minor improvements
""""""""""""""""""

* redfish: simplify interface of Redfish classes (`T365372`_):

  * Now that we have two implementation we can see the common parts and
    simplify a bit the hardcoded bits in both derived classes of the
    Redfish class.
  * Define only the specific service name, not the whole path in the
    concrete classes and define the path in the parent class.
  * Define the service names as class properties instead of instance
    properties to reduce the number of lines and make it more readable, we
    don't really need the strictness of inheritance to ensure we add all
    of them when implementing a new vendor, it's fairly rare.

* mediawiki: update siteinfo URL to use mw-api-int (`T367949`_)

* mysql_legacy: update core sections (`T367496`_):

  * The external storage sections were recently rotated to new ones.

Bug fixes
"""""""""

* mariadb: bugfixes mysql_legacy (`T367496`_):

  * We introduced a number of bugs in spicerack 8.6.0 that needs to be
    handled for automation implementations to begin.
  * Refactored and simplified a bit the new APIs.
  * Added full test coverage.

`v8.6.0`_ (2024-06-12)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* redfish: expand support for Supermicro hosts (`T365372`_):

  * Allow ``RedfishSupermicro`` to be picked up in ``__init__.py`` based on what Netbox returns as manifacturer (and
    not just default to ``RedfishDell``). Update tests to reflect this new behavior.
  * Move ``get_power_state()`` to an abstract method, to be implemented in vendor-specific classes. Update also
    tests to reflect this.

* mysql_legacy: improve support for MariaDB instances on each host (`T343674`_).

Miscellanea
"""""""""""

* redfish: fix typo in DellSCP's class description.

`v8.5.0`_ (2024-04-15)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* netbox: add functions to get and set the device name.
* elasticsearch: remove the dependency from elasticsearch-curator making the calls directly via the elasticsearch
  library (`T345337`_ and `T361647`_).
* alertmanager: add multi-instance and authentication support (`T360932`_):

  * Add support for multiple alertmanager instances based on a configuration file. One of those instances can be
    marked as ``default`` which is used when the call to the ``Spicerack.alertmanager()`` or
    ``Spicerack.alertmanager_hosts()`` API is used without specifying a specific instance or some other API (like
    ``Service.downtime()``) that does not support multiple instances is used.
  * Add support for per-instance HTTP basic authentication. The metricsinfra Alertmanager instance will be behind
    HTTP basic authentication to avoid exposing the read-write API to the entire wikiprod network (via the HTTP
    proxies). This patch adds support for configuring a username and a password to use on a specific Alertmanager
    instance.

Bug fixes
"""""""""

* puppet: make ``PuppetServer.destroy()`` have the same behaviour of ``PuppetMaster.destroy()`` and do not raise an
  exception if the host certificate is already missing (`T360293`_).

Miscellanea
"""""""""""

* setup.py: remove dependency elasticsearch-curator not needed anymore and remove upper bound for black linter that
  was there for incompatibilities with elasticsearch-curator.
* k8s: Remove use of ``@staticmethod`` in tests.
* tests: fix typos in tests that were erroneously calling mock methods with the wrong names.
* utils: remove ``--apply`` from isort's call in format-code, now the default in v5.

`v8.4.1`_ (2024-03-06)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* k8s: add getter for the Batch API.

`v8.4.0`_ (2024-02-27)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* netbox: allow to execute a Netbox script and retrieve the results.
* netbox: add getter/setter for primary IPs and access vlan.

Minor improvements
""""""""""""""""""

* ganeti: pass the v4 and v6 IPs to the VM as ``fw_cfg`` in the create command.

`v8.3.0`_ (2024-01-29)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* ganeti: add support for routed Ganeti (`T300152`_).

Bug fixes
"""""""""

* alertmanager: fix timezone bug when run from a non-UTC computer (`T347490`_).

Miscellanea
"""""""""""

* setup.py: add missing classifier for Python 3.11.

`v8.2.0`_ (2023-11-22)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* puppet: add a ``hiera_lookup()`` method to the ``PuppetServer`` and ``PuppetMaster`` classes to perform a hiera
  lookup of a specific key from the perspective of a specific host.

`v8.1.0`_ (2023-11-20)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* remote: add a new ``RemoteHost.get_subset()`` method return a new ``RemoteHosts`` instance with a subset of the
  hosts. Useful when working with instances that inherit from ``RemoteHostsAdapter`` to be able to work on a subset
  of the hosts.
* service: Add ``ipip_encapsulation`` field to ``ServiceLVS`` to follow what's in Puppet.
* puppet: Update ``get_ca_server`` to also support SRV discovery records.

`v8.0.3`_ (2023-11-16)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* puppet: for the Puppet 7 migration set temporarily the return value of `get_puppet_ca_hostname()` hardcoded to
  ``puppetmaster1001`` to allow to migrate the cumin hosts to Puppet 7.

Miscellanea
"""""""""""

* doc: expand distributed locking docs, add an example of logging when unable to acquire a lock.
* spicerack: log at debug level some stats of each cookbook execution in a machine-readable format. This can be useful
  to generate some stats of the cookbook executions allowing to split them by exit code too.

`v8.0.2`_ (2023-10-18)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* locking: delete the key on etcd if no locks remain to keep etcd clean and avoid to left a lot of keys with emty
  dictionaries as values (`T341973`_).

`v8.0.1`_ (2023-10-18)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* locking: fix path for Spicerack modules locks that was not correctly calculated.

`v8.0.0`_ (2023-10-17)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* dhcp: the ``spicerack.Spicerack.dhcp()`` accessor has changed signature and now accepts just a datacenter name
  instead of ``RemoteHosts`` instance. All cookbooks using this accessor had the same logic implemented to find the
  specific dhcp hosts in a given datacenter and this logic has been moved inside the accessor. All existing usage
  will be migrated at deploy time.
* netbox: remove methods ``fetch_host_status``, ``fetch_host_detail`` and ``put_host_status`` that were deprecated
  since ``v0.0.50`` and replaced by the ``spicerack.netbox.NetboxServer`` class. Some private methods have also been
  renamed to follow more closely Netbox namings.

New features
""""""""""""

* Distributed locking support (`T341973`_):

  * See the dedicated :ref:`Distributed locking<distributed-locking>` section of the documentation for a general
    overview.
  * Cookbooks class API additions to the ``spicerack.cookbook.CookbookRunnerBase`` base class:

    * ``max_concurrency`` class property to statically set the maximum number of concurrent runs of a given cookbook,
      enforced by the distributed lock.
    * ``lock_ttl`` class property to statically set the TTL of the distributed lock acquired for each cookbook run.
    * ``lock_args`` instance property to dynamically modify the locking arguments, for example based on the CLI
      arguments (RO vs RW mode of operations).

  * Cookbooks module API additions:

    * ``MAX_CONCURRENCY`` module constant to statically set the maximum number of concurrent runs of a given cookbook,
      enforced by the distributed lock.
    * ``LOCK_TTL`` module constant to statically set the TTL of the distributed lock acquired for each cookbook run.

  * Automatically acquire a lock for each cookbook run according to the values defined above.
  * spicerack: add a ``_spicerack_lock`` private accessor to get a lock instance to be passed to the Spicerack modules
    that would need to acquire a distributed lock with concurrency and TTL. It is different from the public accessor
    for the cookbooks because the key prefix is different to keep cookbooks custom locks separate from the spicerack
    modules ones. It's mentioned here as information for Spicerack developers.

Minor improvements
""""""""""""""""""

* dhcp: acquire exclusive per-DC lock on write operations:

  * Acquire an exclusive lock on a per-DC basis when performing write operations, both during the creation of a DHCP
    snippet and its deletion.
  * Always rewrite the DHCP snippet. With the protection of the lock, there is no more need for this check and the
    library can safely overwrite all the time the DHCP snippet for a given host.

* puppet: add support for puppetserver JSON commands returning non-zero exit code with JSON output (e.g. if a host is
  missing).

Miscellanea
"""""""""""

* doc: add new section for the distributed locking support in the Introduction page.
* doc: mark the module interface as deprecated instead of having the class one as preferred, to better
  describe the current state.
* tox.ini: remove optimization for tox <4. Tox 4 will not re-use the environments because of the different names,
  so removing this tox <4 optimization as it's making subsequent runs slower with tox 4+.
* dhcp: simplify tests.
* tests: remove obsolete or not anymore needed items from the false positive list of unused code catched by vulture.

`v7.4.1`_ (2023-10-10)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* locking: load also ``~/.etcdrc`` for the running user (`T341973`_):

    * We currently save the authentication credential in ``/root/.etcdrc``. Generically load the effective running
      user's ``~/.etcdrc`` configuration file too and merge it into the one provided in the configuration. This is
      done best effort, if the ~/.etcdrc file is missing it will be silently ignored.

`v7.4.0`_ (2023-10-09)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Add distribted locking support (`T341973`_):

  * locking: add new module for distributed locking support via etcd.
  * spicerack: add a new spicerack accessor ``lock()`` to get an instance of the locking class to acquire and release
    cookbook specific custom locks (`T341973`_).
  * cookbook: add ``--no-locks`` CLI argument to disable locking acquisition/release on a per-run basis. To be used in
    case of emergency or if there are issues with etcd that prevents to acquire/release locks properly.
  * By default the locking support is disabled unless the ``etcd_config`` is set in the configuration file.

Minor improvements
""""""""""""""""""

* spicerack: add ``owner`` property to get a pre-formatted string of the form ``user@host [pid]`` useful to identify
  the owner of a current running process.
* spicerack: add ``current_hostname`` property to get the hostname of the host where the cookbook is currently running.
* spicerack: improve cookbooks help message:

  * The default argument parser in the CookbookBase class doesn't provide a ``prog`` name as it's a bit tricky to
    guess it because it depends on how many cookbooks are defined in a single file.
  * As a result the help message was not very clear up to now::

        $ sudo cookbook sre.hosts.decommission -h
        usage: cookbook [-h] -t TASK_ID [--force] query

  * With this release we inject the cookbook real name in the parser with the additional costruct to use::

        $ sudo cookbook sre.hosts.decommission -h
        usage: cookbook [GLOBAL_ARGS] sre.hosts.decommission [-h] -t TASK_ID [--force] query

  * This way it should also help to remind the user that there are global arguments for the cookbook binary in
    addition to the cookbook-specific ones. It was deemed not necessary to add a message to run ``cookbook -h`` to
    get the available ``GLOBAL_ARGS``, but it can be easily added.

`v7.3.1`_ (2023-10-04)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* tests: fix test that was actually querying the DNS making it fail in the Debian package build process.

`v7.3.0`_ (2023-10-04)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* puppet: Add new ``PuppetServer`` class and make the ``PuppetMaster`` inherit from it as it will be deprecated
  first and then removed in future releases.

Bug fixes
"""""""""

* decorators: fix the ``set_tries()`` function (`T346134`_).

  * It is used to dynamically change the number of tries on a ``@retry``-decorated function/method but was not reading
    the function signature default value when present. Inspect the signature and if the default value is present, is an
    integer and is either untyped or typed as integer use it. Add also tests as they were not present and not spotted
    because the code coverage was considering the function as tested because used in the service module.

Miscellanea
"""""""""""

* tests: simplify the ``spicerack._cookbook.main()`` tests avoiding to mock the Spicerack instance and using instead
  the configuration file to instantiate a real instance.

`v7.2.2`_ (2023-09-11)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* ganeti: add support also for the ``sandbox`` VLAN.
* mediawiki: move the calls to ``noc.wikimedia.org`` to the kubernetes hosted one.

Bug fixes
"""""""""

* puppet: drop deprecated ``--ignorecache`` switch.
* Fix some docstring typos.

Miscellanea
"""""""""""

* spicerack: make all ``CookbookCollection`` class arguments as keyword-only to avoid mistakes (internal API).

`v7.2.1`_ (2023-06-21)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* service: make the ``monitors`` field of the ``ServiceLVS`` class optional to adapt it to the recent change in Puppet
  about it.

`v7.2.0`_ (2023-05-31)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* ganeti: add new ``GanetiRAPI`` methods ``nodes()`` and ``groups()`` to get the related info from the cluster.
* ganeti: specify VM memory size in MB to allow for more fine-tune than GB.
* dhcp: when re-generating the DHCP includes and then restarting the DHCP server, in case of a failure make sure to
  delete the newly created snippet and refresh again to ensure the DHCP is in a good shape.
* dhcp: reword some exception messages.

Miscellanea
"""""""""""

* .gitignore: add local config files to it.
* Add Python 3.11 support.

`v7.1.0`_ (2023-05-15)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* dhcp: expand support for hostname based match using the manufacturer to adapt to different settings.
* remote: improve usability of ``RemoteHosts.wait_reboot_since()`` clarifying the message and making it more DRY-RUN
  friendly.

`v7.0.0`_ (2023-05-08)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* spicerack: refactor IRC logging:

  * Rename the existing ``irc_logger`` to ``sal_logger`` as it logs to IRC with the ``!log`` and hence to SAL.
  * Add a new ``irc_logger`` property to log to IRC on the ``#wikimedia-operations`` channel without the ``!log``
    prefix to just log to IRC and not SAL.

Bug fixes
"""""""""

* doc: do not load UI fix when building the manpage.

`v6.4.3`_ (2023-05-08)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* ganeti: enable ``--no-wait-for-sync`` by default for the virtual machine creation command.

Bug fixes
"""""""""

* decorators: fix ``dry_run`` detection that had a bug in the case of a function with a ``dry_run`` argument with a
  default value. The default value was used also in the presence of a an explicit value set by the caller (`T335855`_).
* doc: fix search in documentation as ``jQuery`` is not automatically loaded by the rtd theme.
* doc: Remove extra preceding space in intro example.

`v6.4.2`_ (2023-04-17)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* kafka: remove setting to avoid checking the hostname in TLS certs as all clusters in production are now running
  with PKI TLS certs that have the hostname in their CN.

Bug fixes
"""""""""

* service: add ``httpbb_dir`` field that was added to the Puppet service catalog.

`v6.4.1`_ (2023-03-30)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* redfish: update log entries location for Dell and make it compatible with different iDRAC versions.

`v6.4.0`_ (2023-03-28)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* tox: make config compatible with tox ``4.x``.
* remote: add results to ``RemoteExecutionError``. While waiting for Cumin to support a more robust result reporting,
  pass the results also in the case of a failed execution to the ``RemoteExecutionError`` excepion so that potentially
  client code could access the partial results on failure using a pattern like::

      try:
          results = remote_hosts.run_sync('some command')
      except RemoteExecutionError as e:
          results = e.results

Bug fixes
"""""""""

* setup.py: force ``dnspython`` from Bullseye pinning the dependency to the same version of Debian Bullseye as
  upstream has breaking changes also between minor versions.
* dnsdisc: adapt code and tests to work with ``dnspython 2.0.0``.
* service: improve ``check_dns_state`` validation check.
* puppet: make the ``PuppetMaster`` class inherit from ``RemoteHostsAdapter`` to fix a bug in dry-run mode with
  a method decorated with ``@retry``.
* service: ensure that ``dry_run`` is passed to the ``Service`` class to be detected in dry-run mode for methods
  decorated with ``@retry``.

Miscellanea
"""""""""""

* tox: use ``sphinx-build`` to generate the documentation, this prevents a deprecation warning for using ``setup.py``.

`v6.3.0`_ (2023-03-15)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* apt: add new module with new ``AptGetHosts`` class that inherits from ``RemoteHostsAdapter`` to handle simple
  ``apt-get`` use cases but setting all the proper options for non-interactive runs of ``apt-get``.
* spicerack: add new ``spicerack.apt_get()`` accessor to run ``apt-get`` commands on target hosts.

Minor improvements
""""""""""""""""""

* redfish: add simple supermicro class.
* alertmanager: match also FQDN, not only hostnames in the label.
* decorators: add ``set_tries()`` function to be used for the ``dynamic_params_callbacks`` argument of the ``@retry``
  decorator to dynamically modify the number of tries to retry from the client.
* dnsdisc: add a ``resolve_with_client_ip()`` method to resolve with EDNS Client Subnet (ECS) support.
* service: extend the discovery capabilities of the service catalog to check the DNS records with ECS support adding
  a ``check_service_ips()`` method and a ``check_dns_state()`` one.
* spicerack: add ``authdns_active_hosts`` property to get a ``RemoteHosts`` instance for the authoritative DNS servers
  currently active. As it uses the Cumin's direct backend it works also if PuppetDB is not available.

Bug fixes
"""""""""

* icinga: handle edge case where status is not optimal but there are no failed services (`T330318`_).
* icinga: uniform code for acked services like failed services to offer the same API in all involved classes.
* k8s: fix existing docstrings.

Miscellanea
"""""""""""

* tox: disable bandit's ``request_without_timeout`` in tests.
* setup.py: bump dependencies minimum version to match those in Debian bullseye.
* setup.py: remove temporary upper limit for prospector as the upstream issue has been fixed.
* doc: dynamically set copyright year to current year.
* Use ``GenericAlias`` objects for type hints in the whole code base given that the lowest supported Python is 3.9:

  * Use directly ``GenericAlias`` builtin objects for type hints (e.g. ``dict[]`` instead of ``Dict[]``).
  * Use directly ``GenericAlias`` objects from the ``collections.abc`` module instead of the ones from the ``typing``
    module (i.e. ``collections.abc.Sequence`` instead of ``typing.Sequence``).
  * See also `PEP 585`_.

* docstrings: automatically document type hints using ``sphinx_autodoc_typehints``. Now it's not necessary to repeat
  in the docstrings the type of the variables and return types as those are automatically added reading the type hints
  present in the signature. The whole code base has been updated accordingly.

`v6.2.2`_ (2023-02-23)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* icinga: fix condition that determines if a service status is failed or not (`T330318`_).
* redfish: ensure versions are parsed as ``packging.version.Version`` instances.

`v6.2.1`_ (2023-02-20)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* tests: revert removal of mocked DNS resolver that prevented the tests to run without network access.

`v6.2.0`_ (2023-02-20)
^^^^^^^^^^^^^^^^^^^^^^

Internal API breaking changes
"""""""""""""""""""""""""""""

* spicerack: get authdns servers from config file (`T329773`_):

  * The list of all authdns servers was retrieved via the cumin alias ``A:dns-auth``, which itself comes from Puppet
    resources (query ``P{R:Class = profile::dns::auth}``).
  * This leads to cookbooks using dnsdisc or service modules failing whenever and authdns is unavailable for
    maintenance.
  * The source of truth for active authdns servers is hiera, so refactor the modules to use a configuration file
    populated by Puppet instead.
  * Using the configuration file from Puppet also removes the need to query the IP of the DNS servers and allows to use
    the Discovery class also withouth a fully working DNS.
  * Use keywords only for most parameters of the touched classes.
  * This change breaks the internal spicerack APIs while the cookbook-facing Spicerack class API has been left
    untouched.

New features
""""""""""""

* alertmanager: add parent ``Alertmanager`` class:

  * In some use cases we need to silence alerts in alertmanager that are not attached to any host via the ``instance``
    label.
  * In order to do so abstract away a higher level ``Alertmanager`` class with the generic bits to interact with the
    Alertmanager APIs and make the existing ``AlertmanagerHosts`` class a derived class of that one.
  * Add a new Spicerack accessor ``alertmanager()`` to get an instance of a generic Alertmanager without relations to
    hosts.

Minor improvements
""""""""""""""""""

* icinga: allow ``wait_for_optimal`` to ignore acknowledged alerts (`T319277`_).
* redfish: allow for refreshing the manager info. Some of the iDRAC info such as firmware and BIOS version are more
  dynamic and as such we gather them every time, however some other data such as the model is fairly static and can
  benefit from being cached. As such update the interface so that we can refresh the specific data block for functions
  that need to.
* redfish: add upload/update methods to push firmware upgrades.

Bug fixes
"""""""""

* mysql_legacy: remove ``x2`` handling logic as it's read-write in both datacenters, and actively written to.
  Remove it from the module's logic completely to avoid confusion and desync with cumin's list of core-db.

`v6.1.0`_ (2023-02-10)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* puppet: allow to specify the exact message when disabling/enabling puppet.
* config: expand user's home (``~``) for logs dir.
* cookbook: improve help message.
* redfish: move Dell specific functionalities to the Dell class.
* redfish: store all OOB info for later use.
* redfish: add ``system_manager`` info and properties for ``bios_version``, ``model``, ``manufacturer``.

Bug fixes
"""""""""

* Fix incorrect usage of ClusterShell's ``NodeSet`` using the Cumin's ``nodeset`` and ``nodeset_fromlist`` instead.

Miscellanea
"""""""""""

* reposync: switch from ``copy_tree`` to ``copytree``.
* kafka: fix typo in docstring.
* dhcp: fix tests using unnecessary hack.
* setup.py: force a newer ``sphinx_rtd_theme``.
* setup.py: pin elasticsearch-curator ``~=5.0``.

`v6.0.0`_ (2022-12-14)
^^^^^^^^^^^^^^^^^^^^^^

Configuration breaking changes
""""""""""""""""""""""""""""""

* The ``cookbooks_base_dir`` config key has been renamed to ``cookbooks_base_dirs`` and must be a list of paths.

New features
""""""""""""

* Add support for multiple cookbooks paths to be loaded. All the cookbooks paths must have a directory inside named
  ``cookbooks/`` and this directory must not have an ``__init__.py`` file as Namespace Packages are used (see
  `PEP 420`_) (`T325168`_).

* Add module injection support (`T319401`_):

  * Add an optional configuration key ``external_modules_dir`` to define an external modules directory that will be
    injected in the Python path to allow to use also external modules not present in spicerack.
  * Add a new ``spicerack.SpicerackExtenderBase`` class to inherit from in order to define an external accessor class
    that will be used by Spicerack to allow to use external accessors.
  * Add an optional configuration key ``extender_class`` in the ``instance_params`` configuration key for specifying
    the fully qualified name of the Python class to use as the extender class.

Miscellanea
"""""""""""

* setup.py: Add ``python_requires`` metadata. The latest pyroma does check for its presence and it makes sense to add
  it to prevent from installing the spicerack package on the wrong Python version.
* setup.py: Revert old upper limit for ``GitPython``, there are no more issue with more recent versions.
* setup.py: Set an upper limit for ``pylint`` and ``prospector`` for upstream issues.
* setup.py: Split the python auto-formatter test dependencies on their own extra group so that they can be installed
  alone in the already split virtual environment for the tox envs ``py3-style`` and ``py3-format``. This way there are
  no conflicts between other test dependencies and ``black`` and ``isort``.
* setup.py: Add specific style tox environments for each Python version to avoid the CI jobs to pick Python 3.7 that
  has a pip backtracking issue with the latest versions of the dependencies. Keep the ``py3-{style,format}``
  environments for ease of use locally and to not break compatibility but make the ``py3-style`` one not run
  automatically in CI.

`v5.0.2`_ (2022-11-17)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* redfish: fix the reboot message ID check for new iDRAC versions.

`v5.0.1`_ (2022-11-17)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* redfish: add reboot message ID for new iDRAC versions.

Miscellanea
"""""""""""

setup.py: remove support from Python 3.7 and 3.8.
tox: remove support from Python 3.7 and 3.8.

`v5.0.0`_ (2022-11-10)
^^^^^^^^^^^^^^^^^^^^^^

Dependencies breaking changes
"""""""""""""""""""""""""""""

* Starting with Spicerack v5.0.0 the support for Python 3.7 and 3.8 is dropped. For now there are no breaking changes
  but it's not guaranteed to work with those versions anymore.

API breaking changes
""""""""""""""""""""

* constants: remove ``CORE_DATACENTERS`` constant:

  * Remove the constant from Spicerack as it's a duplicate of the one already present in ``wmflib``.
  * Convert all Spicerack code to use the same variable from ``wmflib``.
  * All the cookbooks have been already migrated to use the ``wmflib`` one.

Minor improvements
""""""""""""""""""

* ipmi: clarify that the target can also be an IP address. The ipmi module works the same as with a management FQDN.

Bug fixes
"""""""""

* netbox: update allowed state transitions:

  * As the way we use Netbox status is changed as part of the work in `T320696`_ and the ``staged`` status is not
    anymore used, update the allowed transitions based on the new `Server Lifecycle Diagram`_.

Miscellanea
"""""""""""

* mypy: remove upper limit and refactor mypy configuration to properly work with newer versions.

`v4.0.0`_ (2022-09-28)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* redfish: use the management IP instead of FQDN to connect to the management console:

  * Some DELL hosts come with the ``idrac.webserver.HostHeaderCheck`` setting set to ``1``, that prevents to connect
    to the Redfish API unless the hostname is set in the configuration, creating a chicken and egg problem to automate
    the initial setup of the hosts.
  * To prevent this switch the whole module to use directly IPs for now. We might want to improve this later setting
    the hostname in the iDRAC settings and then switching to use the FQDN once that is configured, but because most of
    the automation will be already done by that time it's not clear if it would be a real win.
  * [BREAKING API] this changes the ``spicerack.Spicerack.redfish()`` signature to require a hostname instead of a
    management FQDN and also makes the username parameter optional, defaulting to use ``root``.
  * [BREAKING API] this changes the ``spicerack.redfish.Redfish`` class signature to require a hostname and management
    IP address instead of a single parameter with the FQDN. Although breaking, no cookbook usage should instantiate
    this class directly, but always via the above accessor.

Minor improvements
""""""""""""""""""

* icinga: add explicit support of the DRY-RUN mode (`T315537`_):

  * While the DRY-RUN compatibility of the ``icinga`` module was guaranteed by the ``remote`` module, there was a
    usage of the ``@retry`` decorator that wasn't able to detect when in DRY-RUN mode and accordingly reduce the
    number of retries.

* Bump ``pynetbox`` dependency to ``~= 6.6`` (`T310745`_).
* netbox: enable pynetbox threading (`T311486`_).

Miscellanea
"""""""""""

* doc: fix ``sphinx_checker`` script for Python 3.10.
* doc: add an example on how to use the ``TOX_SKIP_ENV`` environmental variable to run only certain tox environments
  when in development.
* doc: improve documentation of the ``CookbookBase`` classes usage.

`v3.2.1`_ (2022-08-31)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* elasticsearch_cluster: simplify routine to start masters last. Due to the multiple clusters an host can be a master
  in one instance and a child of another instance, bringing the process to a halt using the previous logic. The new
  logic returns all the hosts that are child for all instances first and after that the remaining ones that are
  master for at least one instance.
* peeringdb: minor fixes:

  * Make the ``Spicerack.peeringdb()`` accessor more flexible allowing the configuration file to miss non mandatory
    keys.
  * Add tests for the ``Spicerack.peeringdb()`` accessor.
  * Use empty string as default value for the token to avoid the ``Optional`` type.
  * Fix mypy ignore for type mismatch.
  * Fix various docstrings.

Miscellanea
"""""""""""

* CHANGELOG: fix typos and uniform format.

`v3.2.0`_ (2022-08-18)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""
* peeringdb: add a new module to interact with the PeeringDB API.

Minor improvements
""""""""""""""""""

* elasticsearch_cluster: ensure to restart masters one at a time.

Miscellanea
"""""""""""

* flake8: move flake8's configuration all into ``setup.cfg``.

`v3.1.1`_ (2022-07-26)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* k8s: Increase retry value to prevent timeouts.

Miscellanea
"""""""""""

* Add support for python 3.10.

`v3.1.0`_ (2022-07-20)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* redfish: add support to check the reboot of the DELL iDRACs:

  * add a ``most_recent_member()`` method in the ``Redfish`` class to return the most recent message from an API reply
    with members from Dell.
  * add a ``last_reboot()`` method to the ``Redfish`` class to get the time of the last DELL iDRAC reboot.
  * add a ``wait_reboot_since()`` method to the ``Redfish`` class to poll until the DELL iDRAC comes back online after
    a reboot.

* redfish: add property for the ``HttpPushURI`` url, needed for pushing firmware to the DELL iDRACs.
* redfish: add a ``generation`` property to the ``Redfish`` class to represent the DELL iDRAC genration i.e.
  ``13`` == ``idrac8``, ``14`` == ``idrac9``, and allow us to implment workarounds for older generations.
* redfish: add a ``fqdn()`` getter property and ``__str__()`` method to the ``Redfish`` class:

  * When passing around a ``Redfish`` instance it's useful to know what host it represents as such add a getter for
    the FQDN property and update the ``__str__()`` metbod to also return the FQDN.

* k8s: Add ``KubernetesNode.taints`` propertry to return the taints of a node.
* k8s: Retry checks for expected pods on drain as in some cases (e.g. pods not catching ``TERM``) it might take a while
  for pods to actually terminate. Retry the check for expeced pods to reduce the chance for errors.
* k8s: Retry pod evictions on ``HTTP 429`` from API server:

  * An ``HTTP 429`` response from the API server means that the eviction is not currently allowed because of a
    configured ``PodDisruptionBudget`` or a API server rate limit was hit. Retry ``evict()`` calls in both cases 3
    times with exponential backoff.

* tests: reduce runtime by more than 80%:

  * The logging module setup performed in the ``spicerack._log.setup_logging()`` function is not automatically reset by
    pytest, leading to slowness in some tests, in particular those with a lot of output, for example due to a lot of
    retries.
  * Add a ``_reset_logging_module()`` funtion in the tests for the ``_log`` module that removes all exisiting filters
    and handlers to both the root and the IRC loggers.
  * Call the ``_reset_logging_module()`` function in the teardown of every test that directly or indirectly calls the
    ``spicerack._log.setup_logging()`` function.
  * This reduces the runtime of the unit tests by more than 80%, in my local environment for example it went from ~150s
    to ~25s for the 825 tests run.

Bug fixes
"""""""""

* redfish: better compare Dell SCP attributes:

  * When comparing Dell SCP attributes for the configuration, consider them identical if they are a comma-separated
    list both if the separator is just the comma or comma+space. Some versions of iDRAC return the values comma+space
    separated when getting the current configuration.

* tests: fix ``caplog`` usage:

  * Make sure to use ``caplog.at_level()`` every time the pytest caplog fixture is used to ensure the reliability of
    the test itself and to avoid altering the level for other tests.
  * Rename the ``argparse.py`` test cookbook to ``argparse_ok`` to prevent any conflict with the stdlib argparse
    module.

`v3.0.0`_ (2022-06-28)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* ganeti: refactor the Ganeti module to support the new data model in Netbox:

  * With the new representation of Ganeti data in Netbox, the hardcoded matching between cluster names and Ganeti
    RAPI FQDN endpoint would not work anymore.
  * Refactor the module to gather the data directly from Netbox.
  * This requires the addition of a custom field ``ip_address`` for the virtualization cluster groups model that
    connects it to the Ganeti RAPI VIP "svc" DNS name that is assigned to the related IP address in Netbox.
    The custom field has been already added and populated in Netbox in production.
  * The main benefit is the removal of the hardcoded mapping between clusters and their groups (rows/racks).
  * Add a new ``get_cluster()`` and ``get_group()`` methods in the ``Ganeti`` class to get a new ``GanetiCluster``
    or ``GanetiGroup`` dataclass instances that represent the data required to identify the related resources.
  * Removed the hardcoded magic logic that mapped a row ``A`` to a Ganeti group ``row_A`` as we're moving away from
    row-level redundancy at the network layer towards a rack-level redundancy model. This allows to rename the Ganeti
    groups at anytime freely.

Minor improvements
""""""""""""""""""

* icinga: ensure that the downtime was applied (`T309447`_):

  * Add a ``wait_for_downtimed()`` method that polls the Icinga status to ensure that the hosts got downtimed.
  * Do this best effort, just logging a warning for now in case the downtime can't be verified.

Bug fixes
"""""""""

* redfish: make task polling work with older models that set the end time to Unix epoch at the task start.

Miscellanea
"""""""""""

* log: stop suppressing logging exceptions, that were silenced in the logging configuration.
* doc: fix intersphinx links.

`v2.6.0`_ (2022-06-07)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* redfish: Assume all ``GET`` and ``HEAD`` requests are read-only and anything else is potentally read-write.
* redfish: allow to submit tasks with ``DELETE`` as some Redfish REST API DELETE actions do submit jobs. The
  ``submit_task()`` method accepts an HTTP method different than ``POST`` now.
* netbox: update netbox to use internal discovery address as it got migrated from a public IP to the discovery
  infrastructure.

Miscellanea
"""""""""""

* doc: set default language as Sphinx 5.0+ requires language to not be None when warnings are treated as errors.
* pylint: remove unnecessary comments. The latest pylint has moved the ``no-self-use`` reported issue to an optional
  plugin. We don't need to enable it, hence removing the unnecessary comments.

`v2.5.0`_ (2022-05-26)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* redfish: update signature of the ``request()`` method to support dynamic keyword arguments that will be passed
  directly to the requests library:

  * Although this breaks backward compatibility of the existing API for the ``request()`` method, it's not currently
    used directly anywhere and so it was deemed ok to not justify a new major release for this.
  * In particular the previous ``data`` parameter that was passed to requests's ``json`` parameter would now be passed
    to request's ``data`` parameter, so not being automatically converted to JSON. Existing calls have been modified to
    call ``requests()`` with a ``json`` parameter instead.

New features
""""""""""""

* service: add new module to expose Puppet's ``service::catalog``:

  * Add a new module to load the Puppet ``service::catalog`` hieradata structure into Spicerack.
  * Part of the abstractions allow to access in a more programmatic way the properties of a given service.
  * It also allow to ``depool``/``pool`` (and related context manager) a service in the DNS Discovery realm.
  * It also allow to ``downtime`` (and related context manager) a service in a given datacenter in Alertmanager.
  * See the `service module example usage`_.

Minor improvements
""""""""""""""""""

* reposync: improve git push error handling catching more possible git errors.
* ganeti: add a ``startup()`` method to startup a Ganeti VM (`T306661`_).
* ganeti: add ``set_boot_media()`` method to modify the instance boot media and change it between disk and network
  (PXE) (`T306661`_).
* ganeti: print the output of a Ganeti VM creation while it's being created so that it gets printed live and not at
  only at end.
* dhcp: add to the ``DHCPConfOpt82`` and ``DHCPConfMac`` classes a ``media_type`` parameter:

  * This new ``media_type`` parameter will allow use to easily choose PXE boot media other then the default debian
    installers. Specifically this will allow us to create cookbooks to test specific point releases as well as
    rescue and secure-wipe options.

Bug fixes
"""""""""

* mediawiki: Mediawiki APIs now are only listening only on HTTPS, call the siteinfo API in HTTPS.
* remote: increase the wait for reboot timeout (`T307260`_):

  * In some cases, in particular during reimages, the reboot time can take longer. Increase the limit for now as in most
    cases this will not change anything as the check will succeed way before the timeout.

Miscellanea
"""""""""""

* tests: fix yaml file indentation.
* doc: fix typo.
* setup.py: mark the module as typed so that mypy can type check calls in other tools that are importing this library.

`v2.4.1`_ (2022-04-12)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* elasticsearch_cluster: don't wait for green on first node.
* alertmanager: improve downtime:

  * Allow to pass hosts with already a specific port. If the port is present no port-related regex is added, if the
    port is not present the port-related regex will be automatically added.
  * Optimize the regex adding just once the port regex at the end if all hosts don't have the port specified.
  * Add a matchers parameter to the ``downtime()`` and ``downtimed()`` methods to allow to perform additional filtering
    adding additional matchers.
  * Raise an error in case an additional matcher is trying to target the instance property.

Bug fixes
"""""""""

* alertmanager: fix downtime:

  * Fix the way the matchers for the silence are created. Because AlertManager and Prometheus will evaluate all
    matchers in AND, we can only add one single matcher for the instance property, that has to match all given hosts,
    as opposed to the current implementation that was adding one matcher per host.

`v2.4.0`_ (2022-04-04)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* k8s: add a new module with initial support for Kubernetes that supports draining a node (`T300879`_).
* spicerack: add a new ``Spicerack.thanos()`` accessor to get an instance of ``wmflib.prometheus.Thanos``.
* ipmi: add a ``remove_boot_override()`` method to clear any BIOS boot parameter override because some hosts don't
  automatically clear that after a reboot.

Minor improvements
""""""""""""""""""

* ipmi: improve the ``force_pxe()`` method changing the way it sets the Force PXE bit in the BIOS boot parameters to
  force the reset of the valid flag after a reboot and consider the valid flag as harmless anyway (`T304434`_).

Miscellanea
"""""""""""

* pylint: fix newly reported issue.

`v2.3.3`_ (2022-03-17)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* reposync: don't catch the ``RepoSyncNoChangeError`` allowing the calling cookbook to decide what to do in case of
  no changes in the repository.
* reposync: add a ``force_sync()`` method to perform a force push from the local repository to all remotes.

`v2.3.2`_ (2022-03-10)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* alertmanager: add missing support for dry-run mode.
* reposync: make tests run quicker:

  * Some tests were using ``192.0.2.1`` as a git remote, that doesn't fail immediately, at least on macOS. Replace it
    with a non-existent local path.

`v2.3.1`_ (2022-03-10)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* spicerack: make ``http_session`` more flexible:

  * Instead of updating the signature with the new parameters available in wmflib, relax the signature here in
    spicerack and delegate to wmflib what are the accepted parameters.

Bug fixes
"""""""""

* alertmanager: do not retry on HTTP 500 responses:

  * The Alertmanager API can respond with an HTTP Status Code of 500 on some requests with a valid JSON response,
    although there was no server error (i.e. trying to delete an already deleted silence).
  * Do not retry on 500 responses, allowing requests to get a proper response and then let the module itself decide
    what to do based on the content of the response.

`v2.3.0`_ (2022-03-09)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* alertmanager: catch the already deleted silence error (`T293209`_):

  * The Alertmanager API, when trying to delete an existing silence, returns 500 with a JSON string message in the
    case of an already expired or deleted silence.
  * On delete, catch the exception and just log a warning message in case the silence has been already deleted / is
    already expired.
  * In orther to achieve this, change the ``AlertmanagerError`` exception to accept an optional parameter with the API
    response object.

* elasticsearch_cluster: load the configuration from a yaml file, remove the hardcoded one (`T278378`_).

Miscellanea
"""""""""""

* spicerack: use the private property for the config dir within the class, for coherence.

`v2.2.0`_ (2022-03-08)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* alertmanager: introduced a new module to manage resources on AlertManager (`T293209`_):

  * It has an ``AlertmanagerHosts`` class that currently supports creating a silence (downtime in Icinga terminology)
    and removing it given its ID. It also provides a context manager to perform the silence similarly to the icinga
    module.

* alerting: introduced new alerting module with an ``AlertingHosts`` class as a wrapper around the ``IcingaHosts`` and
  ``AlertmanagerHosts`` classes so that the same actions are performed on both instances.
* spicerack: add accessors for the new ``AlertmanagerHosts`` and ``AlertingHosts`` classes as ``alertmanager_hosts``
  and ``alerting_hosts`` respectively. The preferred way is to use the ``alerting_hosts`` accessor so that actions like
  the downtime are performed on both systems.

Bug fixes
"""""""""

* redfish: fix the default value for the ``allow_new_attributes`` parameter of ``RedfishDell.scp_dump()``.

`v2.1.0`_ (2022-03-03)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* reposync: add new module to manage syncing of automatically generated repositories.

Minor improvements
""""""""""""""""""

* redfish: ``DellSCP``, allow creation of new entities:

  * So far the ``DellSCP`` class allowed only to modify existing attributes in existing components.
  * When dealing with a ``DellSCP`` configuration, there are cases in which it might be necessary to create attributes
    that do not exist in the current configuration. For example when changing the boot mode between ``Bios`` and
    ``Uefi`` a long list of attributes disappear/appear in the configuration.
  * To allow this use case an ``allow_new_attributes`` keyword only parameter has been added to the constructor to
    explicitly allow new attributes, keeping the existing behaviour of typo-protection if that is not passed.
  * Another possible use case is to start from a configuration and create a components section from scratch.
  * To allow this use case an ``empty_components()`` method was added that, while keeping the rest of the configuration
    intact, empties the existing components and from there allows to set new attributes, transparently creating any
    missing component.
  * Add the ``allow_new_attributes`` parameter to ``RedfishDell.scp_dump()`` to enable this new feature when dumping a
    configuration.

Bug fixes
"""""""""

* dhcp: fix lowercase serial tag matching.

Miscellanea
"""""""""""

* setup.py: temporary limit redis library:

  * The latest ``redis`` release v4.1.4 creates some dependency issue, for now limit the upper version as we're anyway
    using v3 in production as that's the version up to Debian Bullseye.

* setup.py: upper limit for black:

  * On Debian bullseye ``elastcisearch-curator`` latest release dependencies have a conflict with black's dependencies
    and it's not possible to put an upper limit to ``elastcisearch-curator`` because previous version don't build
    properly on Bullseye from pip (the debian package version of it has a patch to override its dependency constraints).
  * To prevent conflicts force an upper limit on the black version for now.

* bandit: ignore hardcoded password in tests:

  * Ignore the ``B105:hardcoded_password_string`` and ``B106:hardcoded_password_funcarg`` checks in test directories.
  * Removed related #nosec comments unnecessary now.

* prospector: ignore deprecation message:

  * The latest ``prospector`` issues a deprecated message for the ``pep8`` and ``pep257`` tools that have been renamed
    to ``pycodestyle`` and ``pydocstyle`` respectively. The new names are incompatible with ``prospector < 1.7.0``,
    so for now keep the old names and disable the deprecation warning.

`v2.0.0`_ (2022-02-15)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* management: removed module, it was deprecated in v1.0.0.

New features
""""""""""""

* spicerack: allow to execute another cookbook from within a cookbook:

  * Add the capability from within a cookbook to call another cookbook with custom parameters using the
    ``run_cookbook()`` method in the Spicerack class.
  * The called cookbook will be executed with the same global options with which the current cookbook is running with
    and will log in the same file of the current cookbook run.

Minor improvements
""""""""""""""""""

* redfish: better support of parsing JSON responses (`T299123`_):

  * In some older Dell servers the Redfish API sometimes replies with different casing for the ``MessageId`` key, like
    ``MessageID``.
  * It's also possible that Oem custom messages are reported in the same replies with a different structure.
  * Skip the Oem messages and try both keys cases when parsing the reply.

* redfish: improve support for DRY-RUN mode:

  * In DRY-RUN mode allow read-only requests to be performed (only GET and HEAD) but return a dummy successful
    responses in case of an exception raised by requests (timeout, connection error, etc).
  * In DRY-RUN mode don't allow read-write requests and return a successful dummy response instead.
  * In various methods return a dummy response in DRY-RUN mode.

* dhcp: case-insensitive match of the serial number for the Dell management DHCP requests:

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

* dhcp: use IP address instead of DNS name:

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

* remote: refactor ``wait_reboot_since()``:

  * As the check for uptime is currently either returning a value for all hosts or raising an exception, remove the
    existing logic to check for a partial result as that can't happen.
  * Catch instead the error and re-raise a check exception with a clear message.
  * Also round the printed value of the uptime and the time against which it's checked to 2 decimal values for more
    readability.

Miscellanea
"""""""""""

* setup.py: limit elasticsearch max version:

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

* ipmi: improve dry-run mode for ``force_pxe()``:

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
* doc: add how to contribute section.

`v0.0.59`_ (2021-09-09)
^^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* ipmi: refactor class signature:

  * API breaking change, but the ``Spicerack.ipmi()`` accessor is used only in the ``sre.hosts.decommission`` and
    ``sre.hosts.ipmi-password-reset cookbooks``, so it should be trivial to change both at once.
  * Convert the IPMI class to require the FQDN of the management console to target, to avoid the need to pass that
    around both from the client and internally in the class.
  * The caching of the management password is done transparently by the ``Spicerack.ipmi()`` accessor to avoid the
    anoyance of being asked the management password for each host.

* dhcp: small refactor (the module is still unused):

  * Rename ``switch_port`` to ``switch_iface`` to avoid confusions.
  * Rename the context manager from ``dhcp_push()`` to ``config()`` as it's more natural to use:
    ``with dhcp.config(my_config): # do something``.
  * Simplify formatting of templates, added ignores to vulture for false positives
  * Add constructor documentation to the dataclasses.

* icinga: remove the deprecated ``Icinga`` class:

  * The Icinga class has been deprecated for a while now and it's time to remove it completely. No cookbook is using
    it anymore.

New features
""""""""""""

* remote: add support for the installer key:

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

* puppet: minor improvements:

  * Return the results from the ``Puppet.first_run()`` method to allow to save it to a file like the current reimage
    script does.
  * Add an accessor for the ``master_host`` property in the ``PuppetMaster`` class as this is created and instantiated
    by Spicerack and was hidden from the user of the API.

* decorators: migrate to the wmflib version of ``@retry`` (`T257905`_):

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

* icinga: use shlex to quote the command string for bash (`T288558`_):

  * This fixes the downtiming that would fail if the admin reason contains an apostrophe, due to lack of escaping.

* mediawiki: ignore php-fpm when stopping cronjobs (`T285804`_):

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
* mysql_legacy: re-add ``x2`` database section and add support for active/active core sections (`T285519`_):

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

* mediawiki: Update cronjob code now that most are systemd timers:

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

*  netbox: fix check for server role:

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
* doc: remove obsolete configuration.
* setup.py: add missing tag for Python 3.9, already supported.
* tests: fix pip backtracking separating the prospector tests into its own virtualenv.
* tests: fix format checking:

  * If no Python files were modified at all, the latest isort would bail out. Skipping the checks if no Python files
    were modified at all.

* doc: fix documentation checker for sub-packages:

  * The existing checker was assuming a flat space of modules inside spicerack, while now we have also subpackages.
    Adapt the checker to detect those too.
  * Convert file operations to pathlib.

Miscellanea
"""""""""""

* doc: move ClusterShell URL to HTTPS.
* netbox: refactor unit tests.

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
* logging: improve logging format:

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
* elasticsearch_cluster: Revert the return the cluster name in ``ElasticsearchCluster.__str__`` change added in
  ``v0.0.32``.
* remote: fix pylint typing confusion.

Miscellanea
"""""""""""

* gitignore: add vim swap files.
* tests: temporary force ``mypy`` upper version to avoid a regression in release 0.800.
* tests: tox, enable python 3.9 support.
* code style: introduced ``black`` and ``isort`` as autoformatters (`T211750`_).
* doc: add a development page to highlight how the code is formatted and how to integrate the code formatters
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

* dnsdisc: improve test coverage.
* tests: fix deprecated pytest argument.
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
* doc: refactor and simplify its configuration.
* pylint: allow ``logger`` as module-scope name given that is used throughout the project so that there is no need for
  a pylint disable comment.

`v0.0.43`_ (2020-09-16)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* elasticsearch_cluster: Store which datacenters to query for metrics in Prometheus.

`v0.0.42`_ (2020-08-31)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch_cluster: fix prometheus query syntax.

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
* tests: relax Prospector dependency:

  * The upstream bug that required to set an upper limit on the version of Prospector has been fixed.
  * Removing the upper bound to get newer features.
  * Fix newly reported issues.

* tests: relax Bandit dependency:

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
* doc: fix documentation generation for Sphinx 3.
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

* include the username in logfiles.

`v0.0.32`_ (2020-03-11)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* spicerack: allow to override Spicerack's instance parameters from the configuration file. See :ref:`config.yaml`.
* spicerack: allow to cache the ``Ipmi`` instance so that it can be re-used without re-asking the management password.
* spicerack: expose to cookbooks the ``_spicerack_config_dir`` parameter via a getter.
* netbox: fine tune log and exception messages.
* elasticsearch_cluster: return the cluster name in ``ElasticsearchCluster.__str__``.
* mysql: update ``CORE_SECTIONS`` for external storage RW instances (`T226704`_).

Bug Fixes
"""""""""

* elasticsearch_cluster: add ``https://`` to relforge endpoints.

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
* doc: updated link to the requests module documentation.
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

* Add Netbox module.
* Add the ``LBRemoteCluster`` class to manage cluster behind a load balancer.

Minor improvements
""""""""""""""""""

* icinga: Add a function to force a recheck of all sevices.
* confctl: Add ``filter_objects`` and ``update_objects``.
* confctl: add ``change_and_revert`` contextmanager.

Bug Fixes
"""""""""

* elasticsearch_cluster: correct ports for relforge cluster.
* elasticsearch_cluster: fix ``mypy`` newly reported bug.
* tests: fix ``pytest`` ``caplog`` matching.
* tests: fix ``pep257`` newly reported issues.

`v0.0.25`_ (2019-05-10)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* setup.py: fix ``urllib3`` dependency:

  * In order to build on Debian Stretch without backported packages, relax a bit the urllib3 dependency as the only
    goal for to specify it is to avoid conflicts with the latest version.

* doc: fix Sphinx configuration:

  * In order to avoid issues while building the Debian package on Stretch where Sphinx ``1.4.9`` is available, change
    configuration to:

    * Reduce minimum Sphinx version to ``1.4.9`` in ``setup.py``.
    * Remove the ``warning-is-error`` configuration from ``setup.cfg`` that is applied to every Sphinx run, and move
      it directly into ``tox.ini`` as a command line ``-W`` option, that will be executed only by ``tox`` and not
      during the Debian package build process.

`v0.0.24`_ (2019-05-09)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* prometheus: add timeout support to ``query()`` method.
* ganeti: add timeout support.
* cookbook API: drop ``get_title()`` support:

  * No current cookbook is using the dynamic way to provide a title through ``get_title(args)``.
  * This abstraction has not proven to be useful and the fact to mangle dynamically the title of a cookbook based on
    the current parameter while you can then execute it with different ones doesn't seem very useful, dropping it
    completely from the Cookbook API.

* doc: mark Sphinx warnings as error:

  * To make the documentation building process more robust make Sphinx fail on warnings too.
  * This requires ``Sphinx > 1.5`` and will require to use the backport version while building the package on Debian
    Stretch.

* doc: add checker to ensure modules are documented:

  * It's common when adding a new module to forget to add the few bits required to auto-generated its documentation.
  * Add a check to ensure that all Spicerack modules are listed in the documentation API index and that the linked
    files exists.

Bug Fixes
"""""""""

* ganeti: Fix RAPI port.
* prometheus: fix base URL template.
* doc: autodoc missing API modules.

Miscellanea
"""""""""""

* setup.py: force ``urllib3`` version due to ``pip`` bug.
* Add emacs ignores to gitignore.
* tests: temporarily force ``bandit < 1.6.0``:

    * Due to a bug upstream bandit 1.6.0 doesn't honor the excluded directories, causing the failure of the bandit tox
      environments. Temporarily forcing its version.

`v0.0.23`_ (2019-04-19)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Add basic Ganeti RAPI support.
* Add basic Prometheus support.

Minor improvements
""""""""""""""""""

* elasticsearch_cluster: add reset all indices to read/write capability (`T219799`_).

Bug Fixes
"""""""""

* elasticsearch_cluster: logging during shard allocation was too verbose, some messages lowered to debug level.

Miscellanea
"""""""""""

* flake8: enforce import order and adopt ``W504``:

  * Add ``flake8-import-order`` to enforce the import order using the ``edited`` style that corresponds to our
    styleguide, see: `mediawiki.org: Coding_conventions/Python`_.
  * Mark spicerack as local and do not specify any organization-specific packages to avoid to keep a manually curated
    list of packages.
  * Fix all out of order imports.
  * For line breaks around binary operators, adopt ``W504`` (breaking before the operator) and ignore ``W503``,
    following PEP8 suggestion, see: `PEP0008#line_break_binary_operator`_.
  * Fix all line breaks around binary operators to follow ``W504``.

`v0.0.22`_ (2019-04-04)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch_cluster: use NodesGroup instead of free form JSON.

`v0.0.21`_ (2019-04-03)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* elasticsearch_cluster: Retrieve hostname and fqdn from node attributes.
* elasticsearch_cluster: make unfreezing writes more robust (`T219640`_).
* elasticsearch_cluster: cleanup test by introducing a method to mock API calls.
* elasticsearch_cluster: rename ``elasticsearchclusters`` to ``elasticsearch_clusters``.

Bug Fixes
"""""""""

* tox: fix typo in environment name.

Miscellanea
"""""""""""

* Add Python type hints and mypy check, not for variables and properties as we're still supporting Python 3.5.
* setup.py: revert commit 3d7ab9b that forced the ``urllib3`` version installed as it's not needed anymore.
* tests/doc: unify usage of ``example.com`` domain.

`v0.0.20`_ (2019-03-06)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* ipmi: add password reset functionality.

Minor improvements
""""""""""""""""""

* elasticsearch_cluster: upgrade rows one after the other.
* remote: suppress Cumin's output. As a workaround for a regression in colorama for stretch.
* Expose hostname from Reason.
* elasticsearch_cluster: use the admin Reason to get current hostname.

Bug Fixes
"""""""""

* debmonitor: fix missing variable for logging line.
* elasticsearch_cluster: fix typo (xarg instead of xargs).
* doc: fix reStructuredText formatting.

Miscellanea
"""""""""""

* Drop support for Python 3.4.
* Add support for Python 3.7.
* tests: refactor tox environments.

`v0.0.19`_ (2019-02-21)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch_cluster: support cluster names which have ``-`` in them.
* elasticsearch_cluster: ``get_next_clusters_nodes()`` raises ``ElasticsearchClusterError``.
* elasticsearch_cluster: systemctl iterates explicitly on elasticsearch instances.

Miscellanea
"""""""""""

* setup.py: add ``long_description_content_type``.

`v0.0.18`_ (2019-02-20)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch_cluster: access production clusters over HTTPS.

`v0.0.17`_ (2019-02-20)
^^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* icinga: add ``remove_on_error`` parameter to the ``hosts_downtimed()`` context manager to decide wether to remove
  the downtime or not on error.

Bug Fixes
"""""""""

* elasticsearch_cluster: raise logging level to ERROR for elasticsearch.
* elasticsearch_cluster: retry on all urllib3 exceptions.

`v0.0.16`_ (2019-02-18)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch_cluster: retry on TransportError while waiting for node to be up.
* Change !log formatting to match Stashbot expectations.

`v0.0.15`_ (2019-02-14)
^^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* elasticsearch_cluster: add doc type to delete query.

`v0.0.14`_ (2019-02-13)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* icinga: add context manager for downtimed hosts:

  * Add a context manager to allow to execute other commands while the hosts are downtimed, removing the downtime at
    the end.

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

  * Add a public getter for the owner part of a reason, that retuns in a standard format the user running the code and
    the host where it's running.

Minor improvements
""""""""""""""""""

* decorators: improve tests.
* doc: fine-tune generated documentation.

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

* ipmi: add support for DRY RUN mode.
* config: add load_ini_config() function to parse INI files.
* debmonitor: use the existing configuration file:

  * Instead of requiring a new configuration file, use the existing one already setup by Puppet for the debmonitor
    client.
  * Inject the path of the Debmonitor config into the ctor with a default value.

* puppet: add default ``batch_size`` when running puppet:

  * Allow to specify the ``batch_size`` when running puppet on a set of hosts.
  * Add a default ``batch_size`` to avoid to overload the Puppet master hosts.

Bug Fixes
"""""""""

* phabricator: remove unneded pylint ignore.
* mediawiki: update maintenance host Cumin query.
* remote: add workaround for Cumin bug.

  * To avoid unnecessary waiting on the most common use case of ``reboot()``, that is with only one host, unset the
    default ``batch_sleep`` as a workaround for `T213296`_.

* puppet: fix regenerate_certificate().

  * When re-generating the certificate, Puppet will exit with status code ``1`` both if successful or on failure.
  * Restrict the accepted exit codes to ``1``.
  * Detect errors in the output and raises if any.

`v0.0.11`_ (2019-01-08)
^^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* debmonitor: add debmonitor module.
* phabricator: add phabricator module.

Bug Fixes
"""""""""

* icinga: fix ``command_file`` property.
* puppet: fix ``subprocess`` call to ``check_output()``.
* dns: include ``NXDOMAIN`` in the ``DnsNotFound`` exception.
* admin_reason: fix default value for task.

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

* administrative: fix Reason's signature.
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
.. _`service module example usage`: https://phabricator.wikimedia.org/P24020
.. _`Server Lifecycle Diagram`: https://upload.wikimedia.org/wikipedia/labs/5/56/Server_Lifecycle_Statuses.png
.. _`PEP 420`: https://peps.python.org/pep-0420/
.. _`PEP 585`: https://peps.python.org/pep-0585/

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
.. _`T278378`: https://phabricator.wikimedia.org/T278378
.. _`T285519`: https://phabricator.wikimedia.org/T285519
.. _`T285706`: https://phabricator.wikimedia.org/T285706
.. _`T285803`: https://phabricator.wikimedia.org/T285803
.. _`T285804`: https://phabricator.wikimedia.org/T285804
.. _`T286206`: https://phabricator.wikimedia.org/T286206
.. _`T288558`: https://phabricator.wikimedia.org/T288558
.. _`T289078`: https://phabricator.wikimedia.org/T289078
.. _`T291681`: https://phabricator.wikimedia.org/T291681
.. _`T293209`: https://phabricator.wikimedia.org/T293209
.. _`T299123`: https://phabricator.wikimedia.org/T299123
.. _`T300152`: https://phabricator.wikimedia.org/T300152
.. _`T300879`: https://phabricator.wikimedia.org/T300879
.. _`T304434`: https://phabricator.wikimedia.org/T304434
.. _`T306661`: https://phabricator.wikimedia.org/T306661
.. _`T307260`: https://phabricator.wikimedia.org/T307260
.. _`T309447`: https://phabricator.wikimedia.org/T309447
.. _`T310745`: https://phabricator.wikimedia.org/T310745
.. _`T311486`: https://phabricator.wikimedia.org/T311486
.. _`T315537`: https://phabricator.wikimedia.org/T315537
.. _`T319277`: https://phabricator.wikimedia.org/T319277
.. _`T319401`: https://phabricator.wikimedia.org/T319401
.. _`T320696`: https://phabricator.wikimedia.org/T320696
.. _`T324655`: https://phabricator.wikimedia.org/T324655
.. _`T325168`: https://phabricator.wikimedia.org/T325168
.. _`T329773`: https://phabricator.wikimedia.org/T329773
.. _`T330318`: https://phabricator.wikimedia.org/T330318
.. _`T335855`: https://phabricator.wikimedia.org/T335855
.. _`T336275`: https://phabricator.wikimedia.org/T336275
.. _`T341973`: https://phabricator.wikimedia.org/T341973
.. _`T343674`: https://phabricator.wikimedia.org/T343674
.. _`T345337`: https://phabricator.wikimedia.org/T345337
.. _`T346134`: https://phabricator.wikimedia.org/T346134
.. _`T361647`: https://phabricator.wikimedia.org/T361647
.. _`T347490`: https://phabricator.wikimedia.org/T347490
.. _`T360293`: https://phabricator.wikimedia.org/T360293
.. _`T360932`: https://phabricator.wikimedia.org/T360932
.. _`T362893`: https://phabricator.wikimedia.org/T362893
.. _`T363576`: https://phabricator.wikimedia.org/T363576
.. _`T365372`: https://phabricator.wikimedia.org/T365372
.. _`T365454`: https://phabricator.wikimedia.org/T365454
.. _`T367410`: https://phabricator.wikimedia.org/T367410
.. _`T367496`: https://phabricator.wikimedia.org/T367496
.. _`T367949`: https://phabricator.wikimedia.org/T367949
.. _`T371351`: https://phabricator.wikimedia.org/T371351
.. _`T372485`: https://phabricator.wikimedia.org/T372485
.. _`T373794`: https://phabricator.wikimedia.org/T373794
.. _`T379258`: https://phabricator.wikimedia.org/T379258
.. _`T390860`: https://phabricator.wikimedia.org/T390860

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
.. _`v2.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.1.0
.. _`v2.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.2.0
.. _`v2.3.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.3.0
.. _`v2.3.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.3.1
.. _`v2.3.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.3.2
.. _`v2.3.3`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.3.3
.. _`v2.4.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.4.0
.. _`v2.4.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.4.1
.. _`v2.5.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.5.0
.. _`v2.6.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v2.6.0
.. _`v3.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v3.0.0
.. _`v3.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v3.1.0
.. _`v3.1.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v3.1.1
.. _`v3.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v3.2.0
.. _`v3.2.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v3.2.1
.. _`v4.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v4.0.0
.. _`v5.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v5.0.0
.. _`v5.0.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v5.0.1
.. _`v5.0.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v5.0.2
.. _`v6.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.0.0
.. _`v6.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.1.0
.. _`v6.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.2.0
.. _`v6.2.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.2.1
.. _`v6.2.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.2.2
.. _`v6.3.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.3.0
.. _`v6.4.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.4.0
.. _`v6.4.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.4.1
.. _`v6.4.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.4.2
.. _`v6.4.3`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v6.4.3
.. _`v7.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.0.0
.. _`v7.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.1.0
.. _`v7.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.2.0
.. _`v7.2.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.2.1
.. _`v7.2.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.2.2
.. _`v7.3.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.3.0
.. _`v7.3.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.3.1
.. _`v7.4.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.4.0
.. _`v7.4.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v7.4.1
.. _`v8.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.0.0
.. _`v8.0.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.0.1
.. _`v8.0.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.0.2
.. _`v8.0.3`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.0.3
.. _`v8.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.1.0
.. _`v8.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.2.0
.. _`v8.3.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.3.0
.. _`v8.4.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.4.0
.. _`v8.4.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.4.1
.. _`v8.5.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.5.0
.. _`v8.6.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.6.0
.. _`v8.7.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.7.0
.. _`v8.8.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.8.0
.. _`v8.9.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.9.0
.. _`v8.10.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.10.0
.. _`v8.11.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.11.0
.. _`v8.12.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.12.0
.. _`v8.13.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.13.0
.. _`v8.13.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.13.1
.. _`v8.14.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.14.0
.. _`v8.15.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.15.0
.. _`v8.15.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.15.1
.. _`v8.15.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.15.2
.. _`v8.16.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.16.0
.. _`v8.16.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.16.1
.. _`v8.16.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v8.16.2
.. _`v9.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v9.0.0
.. _`v9.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v9.1.0
.. _`v9.1.1`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v9.1.1
.. _`v9.1.2`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v9.1.2
.. _`v9.1.3`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v9.1.3
.. _`v10.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v10.0.0
.. _`v10.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v10.1.0
.. _`v10.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v10.2.0
.. _`v11.0.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v11.0.0
.. _`v11.1.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v11.1.0
.. _`v11.2.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v11.2.0
.. _`v11.3.0`: https://github.com/wikimedia/operations-software-spicerack/releases/tag/v11.3.0
