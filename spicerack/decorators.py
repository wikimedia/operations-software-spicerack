"""Decorators module."""
import logging
import time
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type, Union, cast

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


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


# TODO: 'func=None' is a workaround for https://github.com/PyCQA/pylint/issues/259
# It was fixed in https://github.com/PyCQA/pylint/pull/2926 but the current Prospector doesn't include yet a recent
# enough version of pylint that has the fix.
# Once fixed restore the signature to 'func: Callable, *' and remove the type: ignore comments.
@ensure_wrap
def retry(
    func: Optional[Callable] = None,
    tries: int = 3,
    delay: timedelta = timedelta(seconds=3),
    backoff_mode: str = "exponential",
    exceptions: Tuple[Type[Exception], ...] = (SpicerackError,),
    failure_message: Optional[str] = None,
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
        failure_message (str, optional): the message to log each time there's a retryable failure. Retry information
            and exception message are also included. Default: "Attempt to run '<fully qualified function>' raised"

    Returns:
        function: the decorated function.

    """
    if not failure_message:
        failure_message = "Attempt to run '{module}.{qualname}' raised".format(
            module=func.__module__, qualname=func.__qualname__  # type: ignore
        )

    @wraps(func)  # type: ignore
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Decorator."""
        if backoff_mode not in ("constant", "linear", "power", "exponential"):
            raise ValueError("Invalid backoff_mode: {mode}".format(mode=backoff_mode))

        if backoff_mode == "exponential" and delay.total_seconds() < 1:
            raise ValueError(
                "Delay must be greater than 1 if backoff_mode is exponential, got {delay}".format(delay=delay)
            )

        if tries < 1:
            raise ValueError("Tries must be a positive integer, got {tries}".format(tries=tries))

        effective_tries = _get_effective_tries(tries, args)
        attempt = 0
        while attempt < effective_tries - 1:
            attempt += 1
            try:
                # Call the decorated function or method
                return func(*args, **kwargs)  # type: ignore
            except exceptions as e:
                sleep = get_backoff_sleep(backoff_mode, delay.total_seconds(), attempt)
                logger.warning(
                    "[%d/%d, retrying in %.2fs] %s: %s",
                    attempt,
                    effective_tries,
                    sleep,
                    failure_message,
                    _exception_message(e),
                )
                time.sleep(sleep)

        return func(*args, **kwargs)  # type: ignore

    return wrapper


def _exception_message(exception: BaseException) -> str:
    """Joins the message of the given exception with those of any chained exceptions.

    Arguments:
        exception (BaseException): The most-recently raised exception.

    Returns:
        str: The joined message, formatted suitably for logging.

    """
    message_parts = [str(exception)]
    while exception.__cause__ is not None or exception.__context__ is not None:
        # __cause__ and __context__ shouldn't both be set, but we use the same logic here as the built-in
        # exception handler, giving __cause__ priority, as described in PEP 3134. We list messages in
        # reverse order from the built-in handler (i.e. newest exception first) since we aren't following a
        # traceback.
        if exception.__cause__ is not None:
            message_parts.append("Caused by: {chained_exc}".format(chained_exc=exception.__cause__))
            exception = exception.__cause__
        else:  # e.__context__ is not None, due to the while condition.
            message_parts.append("Raised while handling: {chained_exc}".format(chained_exc=exception.__context__))
            exception = cast(BaseException, exception.__context__)  # Casting away the Optional.
    return "\n".join(message_parts)


def get_backoff_sleep(backoff_mode: str, base: Union[int, float], index: int) -> Union[int, float]:
    """Calculate the amount of sleep for this attempt.

    Arguments:
        backoff_mode (str): the backoff mode to use for the delay, see the documentation for retry().
        base (int, float): the base for the backoff algorithm.
        index (int): the index to calculate the Nth sleep time for the backoff.

    Return:
        int, float: the amount of sleep to perform for the backoff.

    """
    if backoff_mode == "constant":
        sleep = base
    elif backoff_mode == "linear":
        sleep = base * index
    elif backoff_mode == "power":
        sleep = base * 2 ** (index - 1)
    elif backoff_mode == "exponential":
        sleep = base ** index
    else:
        raise ValueError("Invalid backoff_mode: {mode}".format(mode=backoff_mode))

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
        logger.debug("Decorator called without args")
        return effective_tries

    obj = decorator_args[0]
    if getattr(obj, "_dry_run", False) or getattr(getattr(obj, "_remote_hosts", False), "_dry_run", False):
        logger.warning("Reduce tries from %d to 1 in DRY-RUN mode", tries)
        effective_tries = 1

    return effective_tries
