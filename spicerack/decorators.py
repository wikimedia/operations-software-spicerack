"""Decorators module."""

import inspect
import logging
from collections.abc import Callable
from typing import Any

from wmflib.decorators import RetryParams, ensure_wrap
from wmflib.decorators import retry as wmflib_retry

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


def get_effective_tries(params: RetryParams, func: Callable, args: tuple, kwargs: dict) -> None:
    """Reduce the number of tries to use in the @retry decorator to one when the DRY-RUN mode is detected.

    This is a callback function for the wmflib.decorators.retry decorator.
    The arguments are according to :py:func:`wmflib.decorators.retry` for the ``dynamic_params_callbacks`` argument.

    Arguments:
        params: the decorator original parameters.
        func: the decorated callable.
        args: the decorated callable positional arguments as tuple.
        kwargs: the decorated callable keyword arguments as dictionary.

    """
    reduce_tries = False
    qualname = getattr(func, "__qualname__", "")
    # Detect if func is an instance method that has self ensuring that the name of the class of the first parameter
    # (self) matches the class name extracted from the function's qualname.
    has_self = (
        "." in qualname and args and qualname.rsplit(".", 1)[0] == getattr(getattr(args[0], "__class__"), "__name__")
    )

    # When the decorated object is an instance method
    if has_self and (
        getattr(args[0], "_dry_run", False)  # Has self._dry_run
        or getattr(getattr(args[0], "_remote_hosts", False), "_dry_run", False)  # Has self._remote_hosts
    ):
        reduce_tries = True

    # When the decorated object is a function or method
    if "dry_run" in kwargs:  # Has an explicit dry_run parameter that was set in by the caller, use this one
        if kwargs["dry_run"] is True:
            reduce_tries = True
    else:  # Check if has a dry_run parameter with a default value
        signature_params = inspect.signature(func).parameters
        if "dry_run" in signature_params and signature_params["dry_run"].default is True:
            reduce_tries = True

    if reduce_tries:
        logger.warning("Reduce tries from %d to 1 in DRY-RUN mode", params.tries)
        params.tries = 1


def set_tries(params: RetryParams, func: Callable, _args: tuple, kwargs: dict) -> None:
    """Simple function to allow adapting the number of retries.

    Arguments:
        params: the decorator original parameters.
        func: the decorated callable.
        _args: the decorated callable positional arguments as tuple. Unused.
        kwargs: the decorated callable keyword arguments as dictionary.

    """
    existing_tries = params.tries
    new_tries = None
    if kwargs.get("tries", 0) and isinstance(kwargs["tries"], int):
        new_tries = kwargs["tries"]
    else:  # Check if the signature has an integer default value and is typed as int or untyped
        param = inspect.signature(func).parameters.get("tries")
        if param is not None and param.annotation in (int, inspect.Parameter.empty) and isinstance(param.default, int):
            new_tries = param.default

    if new_tries is not None:
        params.tries = new_tries
        logger.info("Tries set to %s instead of the default %s", new_tries, existing_tries)


@ensure_wrap
def retry(*args: Any, **kwargs: Any) -> Callable:
    """Decorator to retry a function or method if it raises certain exceptions with customizable backoff.

    A customized version of :py:func:`wmflib.decorators.retry` specific to Spicerack:

      * If no exceptions to catch are specified use :py:class:`spicerack.exceptions.SpicerackError`.
      * Always append to the ``dynamic_params_callbacks`` parameter the
        :py:func:`spicerack.decorators.get_effective_tries` function to force the tries parameter to 1 in
        DRY-RUN mode. Appending means that this callback will always be called for last, and eventually override any
        other modification of the tries parameter by other callbacks to 1 when in DRY-RUN mode.

    For the arguments see :py:func:`wmflib.decorators.retry`.

    Returns:
        The decorated function.

    """
    kwargs["dynamic_params_callbacks"] = tuple(list(kwargs.get("dynamic_params_callbacks", [])) + [get_effective_tries])
    kwargs["exceptions"] = kwargs.get("exceptions", (SpicerackError,))

    return wmflib_retry(*args[1:], **kwargs)(args[0])
