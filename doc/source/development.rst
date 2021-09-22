Development
===========

How to contribute
-----------------

See the `Spicerack's Wikitech page`_.

Code style
----------

This project uses the Python automatic code formatter `black`_ in conjunction with `isort`_ and the tests will enforce
that all the Python files are formatted according to the defined style.

In order to automatically format the code while developing, it's possible to integrate black either with the editor/IDE
of choice or directly into the git workflow:

* For the editor/IDE integration see the `black's related`_ page and the `isort's related`_ one.

* For the git workflow integration, that can be done either at commit time or at review time. To do so create either a
  ``pre-commit`` or a ``pre-review`` executable hook file inside the ``.git/hooks/`` directory of the project with the
  following content:

  .. code-block:: bash

      #!/bin/bash

      tox -e py3-format

  The ``pre-commit`` hook will be executed at every commit, while the ``pre-review`` one when running ``git review``.

* If not looking for an automated integration, it's always possible to just manually format the code running:

  .. code-block:: bash

      tox -e py3-format

Git blame
---------

In order to have a cleaner git blame, it might be useful to exclude some specific commits were just cosmetic changes
were made from the history. To do that use:

.. code-block:: bash

    git blame --ignore-revs-file .git-blame-ignore-revs <file>

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
.. _`isort`: https://pycqa.github.io/isort/
.. _`isort's related`: https://pycqa.github.io/isort/#installing-isorts-for-your-preferred-text-editor
.. _`Spicerack's Wikitech page`: https://wikitech.wikimedia.org/wiki/Spicerack#How_to_contribute
