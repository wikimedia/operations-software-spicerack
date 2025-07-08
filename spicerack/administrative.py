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
            reason: the reason to use to justify an administrative action. The username and the hostname where the
                action was originated will be added to the reason automatically. The reason is meant to be passed to
                remote execution in double quotes, allowing to use Bash variables, if needed. Therefore the reason
                cannot contain double quotes.
            username: the username to mention in the reason as the author of the action.
            hostname: the hostname to mention in the reason as the host originating the action.
            task_id: the task ID to mention in the reason.

        Raises:
            spicerack.administrative.ReasonError: if any parameter contains double quotes.

        """
        self._reason = reason
        self._username = username
        self._hostname = hostname
        self._task_id = task_id

    def __setattr__(self, name: str, value: str) -> None:
        """Set an instance attribute with validation.

        Parameters as required by Python's data model, see `object.__setattr__`.

        Raises:
            spicerack.administrative.ReasonError: on validation error of the parameters.

        """
        if value is not None and '"' in value:
            raise ReasonError(f"Property {name} cannot contain double quotes: {value}")

        super().__setattr__(name, value)

    def __str__(self) -> str:
        """String representation of the instance, including all attributes.

        Examples:
            * Example return value when the task ID is not set::

                Given reason - username@hostname

            * Example return value when the task ID is set::

                Given reason - username@hostname - T12345

        """
        parts = [self._reason, self.owner]
        if self._task_id:  # Exclude both None and empty string
            parts.append(self._task_id)

        return " - ".join(parts)

    @property
    def reason(self) -> str:
        """Get the reason given to justify the administrative action."""
        return self._reason

    @property
    def owner(self) -> str:
        """Get the owner of the currently running code.

        Examples:
            Example return value::

                username@hostname

        """
        return f"{self._username}@{self._hostname}"

    @property
    def hostname(self) -> str:
        """Get  the hostname on which the code is running."""
        return self._hostname

    @property
    def task_id(self) -> Optional[str]:
        """Get the task ID to mention in the reason, or :py:data:`None` if none was given."""
        return self._task_id

    def quoted(self) -> str:
        """Get a double quoted string representation of the instance, including all attributes.

        Examples:
            * Example return value when the task ID is not set::

                "Given reason - username@hostname"

            * Example return value when the task ID is set::

                "Given reason - username@hostname - T12345"

        """
        return f'"{self}"'
