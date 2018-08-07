"""Interactive module."""
import os

from spicerack.exceptions import SpicerackError


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


def get_user():
    """Detect and return the effective running user even if run as root.

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
