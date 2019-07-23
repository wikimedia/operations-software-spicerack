"""Decorators module."""
import logging
import time

from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type, Union

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def ensure_wrap(func: Callable) -> Callable:
    """Decorator to wrap other decorators to allow to call them both with and without arguments.

    Arguments:
        func: the decorated function, it must be a decorator. A decorator that accepts only one positional argument
            that is also a callable is not supported.

    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Callable:
        """Decorator wrapper."""
        if len(args) == 1 and not kwargs and callable(args[0]):  # Called without arguments
            return func(args[0])

        return lambda real_func: func(real_func, *args, **kwargs)  # Called with arguments

    return wrapper

# TODO: 'func=None' is a workaround for https://github.com/PyCQA/pylint/issues/259, restore it to 'func, *' once fixed
# and remove the type: ignore comments.
@ensure_wrap
def retry(
    func: Optional[Callable] = None,
    tries: int = 3,
    delay: timedelta = timedelta(seconds=3),
    backoff_mode: str = 'exponential',
    exceptions: Tuple[Type[Exception], ...] = (SpicerackError,)
) -> Callable:
    """Decorator to retry a function or method if it raises certain exceptions with customizable backoff.

    Note:
        The decorated function or method must be idempotent to avoid unwanted side effects.
        It can be called with or without arguments, in the latter case all the default values will be used.

    Note:
        When the decorated function is an instance method of a class, the decorator is able to automatically detect if
        there is a ``self._dry_run`` property in the instance or a ``self._remote_hosts._dry_run`` one and reduce the
        ``tries`` attempts to ``1`` if it's a DRY-RUN to avoid unnecessary waits.

    Arguments:
        func (function, method): the decorated function.
        tries (int, optional): the number of times to try calling the decorated function or method before giving up.
            Must be a positive integer.
        delay (datetime.timedelta, optional): the initial delay for the first retry, used also as the base for the
            backoff algorithm.
        backoff_mode (str, optional): the backoff mode to use for the delay, available values are::

            constant:    delay       => 3, 3,  3,  3,   3, ...;
            linear:      delay * N   => 3, 6,  9, 12,  15, ...; N in [1, tries]
            power:       delay * 2^N => 3, 6, 12, 24,  48, ...; N in [0, tries - 1]
            exponential: delay^N     => 3, 9, 27, 81, 243, ...; N in [1, tries], delay must be > 1.

        exceptions (type, tuple, optional): the decorated function call will be retried if it fails until it succeeds
            or `tries` attempts are reached. A retryable failure is defined as raising any of the exceptions listed.

    Returns:
        function: the decorated function.

    """
    @wraps(func)  # type: ignore
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Decorator."""
        if backoff_mode not in ('constant', 'linear', 'power', 'exponential'):
            raise ValueError('Invalid backoff_mode: {mode}'.format(mode=backoff_mode))

        if backoff_mode == 'exponential' and delay.total_seconds() < 1:
            raise ValueError(
                'Delay must be greater than 1 if backoff_mode is exponential, got {delay}'.format(delay=delay))

        if tries < 1:
            raise ValueError('Tries must be a positive integer, got {tries}'.format(tries=tries))

        effective_tries = _get_effective_tries(tries, args)
        attempt = 0
        while attempt < effective_tries - 1:
            attempt += 1
            try:
                # Call the decorated function or method
                return func(*args, **kwargs)  # type: ignore
            except exceptions as e:
                sleep = get_backoff_sleep(backoff_mode, delay.total_seconds(), attempt)
                logger.warning("Failed to call '%s.%s' [%d/%d, retrying in %.2fs]: %s",
                               func.__module__, func.__name__, attempt, effective_tries, sleep, e)  # type: ignore
                time.sleep(sleep)

        return func(*args, **kwargs)  # type: ignore

    return wrapper


def get_backoff_sleep(backoff_mode: str, base: Union[int, float], index: int) -> Union[int, float]:
    """Calculate the amount of sleep for this attempt.

    Arguments:
        backoff_mode (str): the backoff mode to use for the delay, see the documentation for retry().
        base (int, float): the base for the backoff algorithm.
        index (int): the index to calculate the Nth sleep time for the backoff.

    Return:
        int, float: the amount of sleep to perform for the backoff.

    """
    if backoff_mode == 'constant':
        sleep = base
    elif backoff_mode == 'linear':
        sleep = base * index
    elif backoff_mode == 'power':
        sleep = base * 2 ** (index - 1)
    elif backoff_mode == 'exponential':
        sleep = base ** index
    else:
        raise ValueError('Invalid backoff_mode: {mode}'.format(mode=backoff_mode))

    return sleep


def _get_effective_tries(tries: int, decorator_args: Tuple) -> int:
    """Try to detect if this is a DRY-RUN and reduce the number of tries to one in that case.

    Arguments:
        tries (int): the requested number of tries for the decorator.
        decorator_args (tuple): tuple of positional arguments passed to the decorated function.

    Returns:
        int: the number of tries to use given the requested tries and the detection if this is a DRY-RUN or not.

    """
    effective_tries = tries
    if not decorator_args:
        logger.debug('Decorator called without args')
        return effective_tries

    obj = decorator_args[0]
    if getattr(obj, '_dry_run', False) or getattr(getattr(obj, '_remote_hosts', False), '_dry_run', False):
        logger.warning('Reduce tries from %d to 1 in DRY-RUN mode', tries)
        effective_tries = 1

    return effective_tries
