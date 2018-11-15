"""Administrative module."""
from spicerack.exceptions import SpicerackError


class ReasonError(SpicerackError):
    """Custom exception class for errors of the Reason class."""


class Reason:
    """Class to manage the reason for administrative actions."""

    def __init__(self, reason, username, hostname, *, task_id=''):
        """Initialize the instance.

        Arguments:
            reason (str): the reason to use to justify an administrative action. The username and the hostname where the
                action was originated will be added to the reason automatically. The reason is meant to be passed to
                remote execution in double quotes, allowing to use Bash variables, if needed. Therefore the reason
                cannot contain double quotes.
            username (str): the username to mention in the reason as the author of the action.
            hostname (str): the hostname to mention in the reason as the host originating the action.
            task_id (str, optional): the task ID to mention in the reason.
        """
        self._reason = reason
        self._username = username
        self._hostname = hostname
        self._task_id = task_id

    def __setattr__(self, name, value):
        """Set an instance attribute with validation.

        Parameters:
            As required by Python's data model, see `object.__setattr__`.

        Raises:
            ReasonError: on validation error of the parameters.

        """
        if '"' in value:
            raise ReasonError('Property {name} cannot contain double quotes: {value}'.format(name=name, value=value))

        super().__setattr__(name, value)

    def __str__(self):
        """String representation of the instance, including all attributes.

        Returns:
            str: the generated string representation of all the instance attributes.

        """
        parts = [
            self._reason,
            '{user}@{host}'.format(user=self._username, host=self._hostname),
        ]
        if self._task_id:
            parts.append(self._task_id)

        return ' - '.join(parts)

    def quoted(self):
        """Quoted string representation of the instance, including all attributes.

        Returns:
            str: the generated string representation of all the instance attributes, double quoted.

        """
        return '"{msg}"'.format(msg=self)
