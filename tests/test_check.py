"""Decision-logic tests. Pure functions: no network, no sleeping."""

import pytest

from uptime import check
from uptime.check import DOWN, UP, decide, describe, is_slow

OK = {"ok": True, "status": 200, "ms": 143.0, "error": None}
BAD = {"ok": False, "status": None, "ms": 5000.0, "error": "timed out"}
SLOW = {"ok": True, "status": 200, "ms": 3500.0, "error": None}


# --- state mapping ---------------------------------------------------------

def test_success_maps_to_up():
    assert decide(None, OK)[0] == UP


def test_failure_maps_to_down():
    assert decide(None, BAD)[0] == DOWN


# --- the first check -------------------------------------------------------

def test_first_check_up_does_not_alert():
    """No transition happened yet, and "everything is fine" is noise."""
    state, alert = decide(None, OK)
    assert (state, alert) == (UP, False)


def test_first_check_down_alerts():
    """A target that was already dead must still be reported."""
    state, alert = decide(None, BAD)
    assert (state, alert) == (DOWN, True)


# --- transitions -----------------------------------------------------------

def test_up_to_down_alerts():
    assert decide(UP, BAD) == (DOWN, True)


def test_down_to_up_alerts():
    assert decide(DOWN, OK) == (UP, True)


def test_repeated_down_does_not_alert_again():
    """The whole point: a long outage is one alert, not one per check."""
    assert decide(DOWN, BAD) == (DOWN, False)


def test_repeated_up_does_not_alert():
    assert decide(UP, OK) == (UP, False)


def test_long_outage_produces_exactly_one_alert():
    """Eight failing checks in a row: one alert at the transition."""
    state = None
    alerts = 0
    for _ in range(8):
        state, alert = decide(state, BAD)
        alerts += alert
    assert state == DOWN
    assert alerts == 1


def test_outage_then_recovery_produces_two_alerts():
    state, alerts = None, 0
    for result in (OK, OK, BAD, BAD, BAD, OK, OK):
        state, alert = decide(state, result)
        alerts += alert
    assert alerts == 2  # one going down, one coming back


# --- describe --------------------------------------------------------------

def test_describe_success_line():
    line = describe("example", "https://example.com", OK)
    assert line.startswith("OK")
    assert "example" in line
    assert "200" in line
    assert "143 ms" in line


def test_describe_failure_line():
    line = describe("dead", "https://dead.test", BAD)
    assert line.startswith("DOWN")
    assert "timed out" in line


def test_describe_drops_decimals():
    """{ms:.0f} keeps the line readable."""
    assert "143 ms" in describe("x", "u", {"ok": True, "status": 200,
                                           "ms": 142.7, "error": None})


# --- slow detection --------------------------------------------------------

def test_slow_is_true_only_when_it_answered_slowly():
    assert is_slow(SLOW) is True


def test_fast_response_is_not_slow():
    assert is_slow(OK) is False


def test_failure_is_not_slow():
    """A timeout is DOWN, not slow — reporting both would double-count it."""
    assert is_slow(BAD) is False