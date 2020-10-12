"""Actions module."""
import logging

from typing import Hashable, List


logger = logging.getLogger(__name__)


class Actions:
    """Class to keep track and log a set of actions performed and their result with a nice string representation."""

    def __init__(self, name: Hashable):
        """Initialize the instance.

        When converted to string returns a nicely formatted representation of the instance and all its actions.

        It exposes the following properties:

        - ``name``: the name passed to the instance at instantiation time.

        - ``has_warnings``: a :py:class:`bool` that is :py:data:`True` when at least one warning action was registered,
          :py:data:`False` otherwise.

        - ``has_failures``: a :py:class:`bool` that is :py:data:`True` when at least one failed action was registered,
          :py:data:`False` otherwise.

        Arguments:
            name (typing.Hashable): the name of the set of actions to be registered.

        """
        self.name = name
        self.actions: List[str] = []
        self.has_warnings = False
        self.has_failures = False

    def __str__(self) -> str:
        """Custom string representation of the actions performed.

        Returns:
            str: the string representation.

        """
        actions = '\n'.join('  - {action}'.format(action=action) for action in self.actions)
        return '{name} (**{status}**)\n{actions}'.format(name=self.name, status=self.status, actions=actions)

    @property
    def status(self) -> str:
        """Return the current status of the actions based on the worst result recorded.

        Returns:
            str: the short string representation of the status, one of: ``PASS``, ``WARN``, ``FAIL``.

        """
        if self.has_failures:
            return 'FAIL'
        if self.has_warnings:
            return 'WARN'

        return 'PASS'

    def success(self, message: str) -> None:
        """Register a successful action.

        Arguments:
            message (str): the action description.

        """
        self._action(logging.INFO, message)

    def failure(self, message: str) -> None:
        """Register a failed action.

        Arguments:
            message (str): the action description.

        """
        self._action(logging.ERROR, message)
        self.has_failures = True

    def warning(self, message: str) -> None:
        """Register an action that require some attention.

        Arguments:
            message (str): the action description.

        """
        self._action(logging.WARNING, message)
        self.has_warnings = True

    def _action(self, level: int, message: str) -> None:
        """Register a generic action.

        Arguments:
            level (int): a logging level integer to register the action for.
            message (str): the action description.

        """
        logger.log(level, message)
        self.actions.append(message)


class ActionsDict(dict):
    """Custom dictionary with defaultdict capabilities for the :py:class:`spicerack.actions.Action` class.

    Automatically instantiate and returns a new instance of the :py:class:`spicerack.actions.Actions` class for every
    missing key like a :py:class:`collections.defaultdict`.

    When accessing a missing key, the key itself is passed to the new :py:class:`spicerack.actions.Actions` instance
    as ``name``.

    When converted to string returns a nicely formatted representation of the instance and all its items.
    """

    def __missing__(self, key: Hashable) -> Actions:
        """Instantiate a new Actions instance for the missing key like a defaultdict.

        Parameters as required by Python's data model, see :py:method:`object.__missing__`.

        """
        self[key] = Actions(key)
        return self[key]

    def __str__(self) -> str:
        """Custom string representation of the instance.

        Returns:
            str: the string representation.

        """
        return '\n'.join('- {actions}\n'.format(actions=value) for key, value in self.items())
