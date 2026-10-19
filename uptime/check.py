"""Check one URL and decide whether the change deserves an alert.

Split like the scraper repo: the network call sits at the edge, and the
decision in the middle is a pure function so it can be tested offline.
"""

import time
import urllib.error
import urllib.request

# The two states a target can be in.
UP = "up"
DOWN = "down"

# Above this many seconds a reply counts as slow. Not a definition of "down",
# only a note in the report.
SLOW_SECONDS = 2.0


def check_once(url: str, timeout: float = 5.0) -> dict:
    """Request a URL and report whether it answered, with timing."""
    # perf_counter is a monotonic stopwatch: it cannot jump backwards if the
    # system clock is adjusted.
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            elapsed = (time.perf_counter() - started) * 1000  # milliseconds
            return {"ok": True, "status": response.status, "ms": elapsed, "error": None}
    except urllib.error.HTTPError as e:
        # The server answered with an error code (404, 500). The connection
        # worked, but from a monitoring point of view the service is not
        # healthy, so this counts as down.
        elapsed = (time.perf_counter() - started) * 1000
        return {"ok": False, "status": e.code, "ms": elapsed, "error": f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        # No answer at all: DNS failure, connection refused, timeout.
        elapsed = (time.perf_counter() - started) * 1000
        return {"ok": False, "status": None, "ms": elapsed, "error": str(e)}


def decide(previous: str | None, result: dict) -> tuple[str, bool]:
    """Return the new state and whether this change deserves an alert.

    Pure: takes a previous state and a check result, returns a decision. The
    alert rule is what separates a monitor from a ping loop — a long outage is
    ONE message, not one per check.
    """
    current = UP if result["ok"] else DOWN

    # The first check has no previous state, so no transition can be compared.
    # Its own rule: report only if the target is already down, otherwise the
    # "all good" message is pure noise.
    if previous is None:
        return current, current == DOWN

    # Otherwise alert exactly on a change of state.
    return current, current != previous


def summary(result: dict) -> str:
    """The changing part of a line: status code + time, or the error + time.

    Kept separate from describe() so an alert line does not repeat the status
    word ("DOWN ... down").
    """
    if result["ok"]:
        return f"{result['status']} in {result['ms']:.0f} ms"
    return f"{result['error']} after {result['ms']:.0f} ms"


def describe(name: str, url: str, result: dict) -> str:
    """Format one check result as a single line, for a report."""
    # "OK  " carries two extra spaces so the columns line up with "DOWN".
    word = "OK  " if result["ok"] else "DOWN"
    return f"{word} {name:<12} {summary(result)}"


def is_slow(result: dict) -> bool:
    """True when the target answered, but took too long."""
    return bool(result["ok"]) and result["ms"] > SLOW_SECONDS * 1000