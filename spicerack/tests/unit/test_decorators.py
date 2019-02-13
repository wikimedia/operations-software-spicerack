"""Dnsdisc module tests."""
from datetime import timedelta
from unittest import mock

import pytest

from spicerack.decorators import get_backoff_sleep, retry
from spicerack.exceptions import SpicerackError


class DryRunRetry:
    """Test class to simulate any Spicerack class with a ``_dry_run`` property."""

    def __init__(self, dry_run=True):
        """Initialize the ``_dry_run`` property."""
        self._dry_run = dry_run

    @retry
    def fail(self):
        """A method that fail always to trigger the retry logic."""
        raise SpicerackError('self._dry_run={d}'.format(d=self._dry_run))


def _generate_mocked_function(calls):
    func = mock.Mock()
    func.side_effect = calls
    func.__name__ = 'mocked'
    return func


@pytest.mark.parametrize('calls, sleep_calls', (
    ([True], []),
    ([SpicerackError('error1'), True], [3.0]),
    ([SpicerackError('error1'), SpicerackError('error2'), True], [3.0, 9.0]),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_pass_no_args(mocked_sleep, calls, sleep_calls):
    """Using @retry with no arguments should use the default values."""
    func = _generate_mocked_function(calls)
    ret = retry(func)()
    assert ret
    func.assert_has_calls([mock.call()] * len(calls))
    mocked_sleep.assert_has_calls([mock.call(i) for i in sleep_calls])


@pytest.mark.parametrize('dry_run', (True, False))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_pass_no_args_dry_run(mocked_sleep, dry_run):
    """Using @retry with no arguments should use the default values but set tries to 1 if in DRY-RUN."""
    obj = DryRunRetry(dry_run=dry_run)
    with pytest.raises(SpicerackError):
        obj.fail()

    sleep_call_count = 2
    if dry_run:
        sleep_call_count = 0
    assert mocked_sleep.call_count == sleep_call_count


@pytest.mark.parametrize('exc, calls, sleep_calls', (
    (SpicerackError, [SpicerackError('error')] * 3, [3.0, 9.0]),
    (Exception, [Exception('error')], []),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_fail_no_args(mocked_sleep, exc, calls, sleep_calls):
    """Using @retry with no arguments should raise the exception raised by the decorated function if not cathced."""
    func = _generate_mocked_function(calls)
    with pytest.raises(exc, match='error'):
        retry(func)()

    func.assert_has_calls([mock.call()] * len(calls))
    mocked_sleep.assert_has_calls([mock.call(i) for i in sleep_calls])


@pytest.mark.parametrize('calls, sleep_calls, kwargs', (
    ([True], [], {'delay': timedelta(seconds=11), 'tries': 1}),
    ([Exception('error1'), True], [5.55],
     {'delay': timedelta(seconds=5, milliseconds=550), 'tries': 2, 'exceptions': Exception}),
    ([SpicerackError('error1'), True], [8.88],
     {'backoff_mode': 'exponential', 'delay': timedelta(milliseconds=8880), 'tries': 2}),
    ([SpicerackError('error1'), True], [0.90],
     {'backoff_mode': 'power', 'delay': timedelta(milliseconds=900), 'tries': 2}),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_pass_args(mocked_sleep, calls, sleep_calls, kwargs):
    """Using @retry with arguments should use the soecified values."""
    func = _generate_mocked_function(calls)
    ret = retry(**kwargs)(func)()

    assert ret
    func.assert_has_calls([mock.call()] * len(calls))
    mocked_sleep.assert_has_calls([mock.call(i) for i in sleep_calls])


@pytest.mark.parametrize('exc, kwargs', (
    (SpicerackError, {}),
    (RuntimeError, {'exceptions': (KeyError, ValueError)}),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_fail_args(mocked_sleep, exc, kwargs):
    """Using @retry with arguments should raise the exception raised by the decorated function if not cathced."""
    func = _generate_mocked_function([exc('error')])
    kwargs['tries'] = 1
    with pytest.raises(exc, match='error'):
        retry(**kwargs)(func)()

    func.assert_called_once_with()
    assert not mocked_sleep.called


@pytest.mark.parametrize('kwargs, message', (
    ({'tries': 0}, 'Tries must be a positive integer, got 0'),
    ({'backoff_mode': 'invalid'}, 'Invalid backoff_mode: invalid'),
    ({'backoff_mode': 'exponential', 'delay': timedelta(milliseconds=500)},
     'Delay must be greater than 1 if backoff_mode is exponential'),
))
def test_retry_invalid(kwargs, message):
    """Using @retry with invalid arguments should raise ValueError."""
    with pytest.raises(ValueError, match=message):
        retry(**kwargs)(lambda: True)()  # pylint: disable=not-callable


@pytest.mark.parametrize('mode, base, values', (
    ('constant', 0, (0,) * 5),
    ('constant', 0.5, (0.5,) * 5),
    ('constant', 3, (3,) * 5),
    ('linear', 0, (0,) * 5),
    ('linear', 0.5, (0.5, 1.0, 1.5, 2.0, 2.5)),
    ('linear', 3, (3, 6, 9, 12, 15)),
    ('power', 0, (0,) * 5),
    ('power', 0.5, (0.5, 1, 2, 4, 8)),
    ('power', 3, (3, 6, 12, 24, 48)),
    ('exponential', 1, (1,) * 5),
    ('exponential', 1.5, (1.5, 2.25, 3.375, 5.0625, 7.59375)),
    ('exponential', 3, (3, 9, 27, 81, 243)),
))
def test_get_backoff_sleep(mode, base, values):
    """Calling get_backoff_sleep() should return the proper backoff based on the arguments."""
    for i, val in enumerate(values, start=1):
        assert get_backoff_sleep(mode, base, i) == pytest.approx(val)


def test_get_backoff_sleep_raise():
    """Calling get_backoff_sleep() with an invalid backoff_mode should raise ValueError."""
    with pytest.raises(ValueError, match='Invalid backoff_mode: invalid'):
        get_backoff_sleep('invalid', 1, 5)
