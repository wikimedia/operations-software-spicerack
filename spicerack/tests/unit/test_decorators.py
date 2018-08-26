"""Dnsdisc module tests."""
from datetime import timedelta
from unittest import mock

import pytest

from spicerack.decorators import get_backoff_sleep, retry
from spicerack.exceptions import SpicerackError

from spicerack.tests import caplog_not_available


def _generate_mocked_function(calls):
    func = mock.Mock()
    func.side_effect = calls
    func.__name__ = 'mocked'
    return func


@pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
@pytest.mark.parametrize('calls, messages', (
    ([True], []),
    ([SpicerackError('error1'), True], ["Failed to call 'unittest.mock.mocked' [1/3, retrying in 3.00s]: error1"]),
    ([SpicerackError('error1'), SpicerackError('error2'), True],
     ["Failed to call 'unittest.mock.mocked' [1/3, retrying in 3.00s]: error1",
      "Failed to call 'unittest.mock.mocked' [2/3, retrying in 9.00s]: error2"]),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_pass_no_args(mocked_sleep, calls, messages, caplog):
    """Using @retry with no arguments should use the default values."""
    func = _generate_mocked_function(calls)
    ret = retry(func)()
    print(mocked_sleep.mock_calls)
    assert ret
    for message in messages:
        assert message in caplog.text
    func.assert_has_calls([mock.call()] * len(calls))


@pytest.mark.parametrize('exc, calls', (
    (SpicerackError, [SpicerackError('error')] * 3),
    (Exception, [Exception('error')]),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_fail_no_args(mocked_sleep, exc, calls):
    """Using @retry with no arguments should raise the exception raised by the decorated function if not cathced."""
    func = _generate_mocked_function(calls)
    with pytest.raises(exc, match='error'):
        retry(func)()

    print(mocked_sleep.mock_calls)
    func.assert_has_calls([mock.call()] * len(calls))


@pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
@pytest.mark.parametrize('calls, messages, kwargs', (
    ([True], [], {'delay': timedelta(seconds=11), 'tries': 1}),
    ([Exception('error1'), True],
     ["Failed to call 'unittest.mock.mocked' [1/2, retrying in 5.55s]: error1"],
     {'delay': timedelta(seconds=5, milliseconds=550), 'tries': 2, 'exceptions': Exception}),
    ([SpicerackError('error1'), True],
     ["Failed to call 'unittest.mock.mocked' [1/2, retrying in 8.88s]: error1"],
     {'backoff_mode': 'exponential', 'delay': timedelta(milliseconds=8880), 'tries': 2}),
    ([SpicerackError('error1'), True],
     ["Failed to call 'unittest.mock.mocked' [1/2, retrying in 0.90s]: error1"],
     {'backoff_mode': 'power', 'delay': timedelta(milliseconds=900), 'tries': 2}),
))
@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_retry_pass_args(mocked_sleep, calls, messages, kwargs, caplog):
    """Using @retry with arguments should use the soecified values."""
    func = _generate_mocked_function(calls)
    ret = retry(**kwargs)(func)()

    print(mocked_sleep.mock_calls)
    assert ret
    for message in messages:
        assert message in caplog.text
    func.assert_has_calls([mock.call()] * len(calls))


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

    print(mocked_sleep.mock_calls)
    func.assert_called_once_with()


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
