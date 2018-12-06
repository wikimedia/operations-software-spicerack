"""Interactive module."""
import getpass
import logging
import os

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def ask_confirmation(message):
    """Ask the use for confirmation in interactive mode.

    Arguments:
        message (str): the message to be printed before asking for confirmation.

    Raises:
        SpicerackError: on too many invalid answers.

    """
    print(message)
    print('Type "done" to proceed')

    for _ in range(3):
        resp = input('> ')
        if resp == 'done':
            break

        print('Invalid response, please type "done" to proceed. After 3 wrong answers the task will be aborted.')
    else:
        raise SpicerackError('Too many invalid confirmation answers')


def get_username():
    """Detect and return the name of the effective running user even if run as root.

    Returns:
        str: the name of the effective running user or '-' if unable to detect it.

    """
    user = os.getenv('USER')
    sudo_user = os.getenv('SUDO_USER')

    if sudo_user is not None and sudo_user != 'root':
        return sudo_user

    if user is not None:
        return user

    return '-'


def ensure_shell_is_durable():
    """Ensure it is running either in non-interactive mode or in a screen/tmux session, raise otherwise.

    Raises:
        spicerack.exceptions.SpicerackError: if in a non-durable shell session.

    """
    if (os.isatty(0) and not os.getenv('STY', '') and not os.getenv('TMUX', '') and
            'screen' not in os.getenv('TERM', '')):
        raise SpicerackError('Must be run in non-interactive mode or inside a screen or tmux.')


def get_management_password():
    """Get the management password either from the environment or asking for it.

    Returns:
        str: the password.

    Raises:
        spicerack.exceptions.SpicerackError: if the password is empty.

    """
    password = os.getenv('MGMT_PASSWORD')

    if password is None:
        logger.debug('MGMT_PASSWORD environment variable not found')
        # Ask for a password, raise exception if not a tty
        password = getpass.getpass(prompt='Management Password: ')
    else:
        logger.info('Using Management Password from the MGMT_PASSWORD environment variable')

    if not password:
        raise SpicerackError('Empty Management Password')

    return password
