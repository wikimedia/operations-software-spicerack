"""Administrative module."""
from typing import Optional

from spicerack.exceptions import SpicerackError


class ReasonError(SpicerackError):
    """Custom exception class for errors of the Reason class."""


class Reason:
    """Class to manage the reason for administrative actions."""

    def __init__(self, reason: str, username: str, hostname: str, *, task_id: Optional[str] = None) -> None:
        """Initialize the instance.

        Arguments:
            reason (str): the reason to use to justify an administrative action. The username and the hostname where the
                action was originated will be added to the reason automatically. The reason is meant to be passed to
                remote execution in double quotes, allowing to use Bash variables, if needed. Therefore the reason
                cannot contain double quotes.
            username (str): the username to mention in the reason as the author of the action.
            hostname (str): the hostname to mention in the reason as the host originating the action.
            task_id (str, optional): the task ID to mention in the reason.

        Raises:
            spicerack.administrative.ReasonError: if any parameter contains double quotes.

        """
        self._reason = reason
        self._username = username
        self._hostname = hostname
        self._task_id = task_id

    def __setattr__(self, name: str, value: str) -> None:
        """Set an instance attribute with validation.

        Parameters:
            As required by Python's data model, see `object.__setattr__`.

        Raises:
            ReasonError: on validation error of the parameters.

        """
        if value is not None and '"' in value:
            raise ReasonError('Property {name} cannot contain double quotes: {value}'.format(name=name, value=value))

        super().__setattr__(name, value)

    def __str__(self) -> str:
        """String representation of the instance, including all attributes.

        Returns:
            str: the generated string representation of all the instance attributes.

        """
        parts = [self._reason, self.owner]
        if self._task_id is not None:
            parts.append(self._task_id)

        return ' - '.join(parts)

    @property
    def owner(self) -> str:
        """Getter for the owner property.

        Returns:
            str: the origin (user@host) of the currently running code.

        """
        return '{user}@{host}'.format(user=self._username, host=self._hostname)

    @property
    def hostname(self) -> str:
        """Getter for the hostname property.

        Returns:
            str: the hostname on which the code is running.

        """
        return self._hostname

    def quoted(self) -> str:
        """Quoted string representation of the instance, including all attributes.

        Returns:
            str: the generated string representation of all the instance attributes, double quoted.

        """
        return '"{msg}"'.format(msg=self)
