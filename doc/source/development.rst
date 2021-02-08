Development
===========

Code style
----------

This project uses the Python automatic code formatter `black`_ and the tests will enforce that all the Python files are
formatted according to black's format.

In order to automatically format the code while developing, it's possible to integrate black either with the editor/IDE
of choice or directly into the git workflow:

For the editor/IDE integration see the `black's related`_ page.

For the git workflow integration, that can be done either at commit time or at review time. To do so create either a
``pre-commit`` or a ``pre-review`` executable hook file inside the ``.git/hooks/`` directory of the project with the
following content:

.. code-block:: bash

    #!/bin/bash

    tox -e py3-format

The ``pre-commit`` hook will be executed at every commit, while the ``pre-review`` one when running ``git review``.

Running tests
-------------

The ``tox`` utility, a wrapper around virtualenv, is used to run the tests. To list the default environments that
will be executed when running ``tox`` without parameters, run:

.. code-block:: bash

    tox -lv

To list all the available environments:

.. code-block:: bash

    tox -av

To run one specific environment only:

.. code-block:: bash

    tox -e py39-flake8

It's possible to pass extra arguments to the underlying environment:

.. code-block:: bash

    # Run only tests in a specific file:
    tox -e py39-unit -- -k test_remote.py

    # Run only one specific test:
    tox -e py38-unit -- -k test_spicerack_netbox


.. _`black`: https://github.com/psf/black
.. _`black's related`: https://github.com/psf/black/blob/master/docs/editor_integration.md
