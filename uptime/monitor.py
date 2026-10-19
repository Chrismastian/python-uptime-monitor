"""Uptime monitor: poll configured targets and alert only on state changes.

The scheduling shape is the earlier job-queue pattern (a loop plus state), and
the decision logic lives in check.decide, which is pure and testable.
"""

import json
import time
from pathlib import Path

from .check import DOWN, UP, check_once, decide, describe, is_slow, summary
from .config import CONFIG_FILE, interval_of, load_config

# Where the last known state of each target is kept between runs. Persisting it
# is what lets the monitor survive a restart without re-alerting every target
# that is already down.
STATE_FILE = Path("state.json")


def load_state(path: Path = STATE_FILE) -> dict:
    """Read the previous state map. Return {} when there is no file yet."""
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    """Persist the state map so a restart does not re-alert."""
    path.write_text(json.dumps(state, indent=2), "utf-8")


def run_round(config: dict, state: dict, notifier) -> tuple[dict, list[str]]:
    """Check every target once. Return (new state, alert messages).

    Pure with respect to the network: check_once does the I/O, decide makes the
    call, and the notifier is passed in so tests can collect messages instead
    of printing them.
    """
    alerts = []

    for target in config["targets"]:
        name = target["name"]
        url = target["url"]

        result = check_once(url)
        previous = state.get(name)
        current, should_alert = decide(previous, result)
        state[name] = current

        line = describe(name, url, result)
        if should_alert:
            # The transition is what matters, so the alert names the change and
            # does not repeat the status word that the log line already carries.
            direction = "DOWN" if current == DOWN else "BACK UP"
            message = f"[{direction}] {name}: {summary(result)}"
            alerts.append(message)
            notifier(message)
        else:
            notifier(f"     {line}")

        if is_slow(result):
            notifier(f"     (slow) {name} took {result['ms']:.0f} ms")

    return state, alerts


def run_monitor(config_path: Path = CONFIG_FILE, rounds: int | None = None,
                notifier=print, sleep=time.sleep) -> dict:
    """Poll forever, or for `rounds` rounds when given (used by tests/demos)."""
    config = load_config(config_path)
    interval = interval_of(config)
    state = load_state()

    completed = 0
    while rounds is None or completed < rounds:
        notifier(f"--- round {completed + 1} at {time.strftime('%H:%M:%S')} ---")
        state, alerts = run_round(config, state, notifier)
        save_state(state)
        notifier(f"    {len(alerts)} alert(s), {len(state)} target(s) tracked")
        completed += 1

        if rounds is None or completed < rounds:
            sleep(interval)  # the scheduling: wait, then poll again

    return state


if __name__ == "__main__":
    try:
        run_monitor()
    except KeyboardInterrupt:
        # Ctrl+C is the normal way to stop a forever-running monitor.
        print("\nstopped")