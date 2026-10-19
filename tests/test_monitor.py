"""Round-level tests: real HTTP against a local server, no internet needed."""

import http.server
import json
import threading

import pytest

from uptime import monitor
from uptime.config import interval_of, validate


class Quiet(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def live_server():
    """A real HTTP server that can be stopped mid-test (a dead target)."""
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Quiet)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/"
    httpd.shutdown()
    httpd.server_close()


def config_for(url: str) -> dict:
    return {"interval": 1, "targets": [{"name": "local", "url": url}]}


def test_round_marks_a_reachable_target_up(live_server):
    lines = []
    state, alerts = monitor.run_round(config_for(live_server), {}, lines.append)

    assert state == {"local": "up"}
    assert alerts == []
    assert any("OK" in line for line in lines)


def test_round_marks_a_dead_port_down(live_server):
    # Point at a port nothing listens on: a refused connection.
    dead = live_server.replace(live_server.rsplit(":", 1)[1].rstrip("/"), "1")
    lines = []
    state, alerts = monitor.run_round(config_for(dead), {}, lines.append)

    assert state == {"local": "down"}
    assert len(alerts) == 1                    # first check of a dead target
    assert alerts[0].startswith("[DOWN]")


def test_second_round_of_a_dead_target_is_silent(live_server):
    dead = live_server.replace(live_server.rsplit(":", 1)[1].rstrip("/"), "1")
    config = config_for(dead)
    state = {}

    _, first = monitor.run_round(config, state, lambda _m: None)
    _, second = monitor.run_round(config, state, lambda _m: None)

    assert len(first) == 1    # the transition
    assert second == []       # still down: nothing new to report


def test_recovery_after_outage_alerts_once(live_server):
    """up -> down -> up: two alerts total."""
    config = config_for(live_server)
    state = {}
    noise = lambda _m: None

    monitor.run_round(config, state, noise)                       # up, silent
    state["local"] = "down"                                       # pretend it died
    _, alerts = monitor.run_round(config, state, noise)           # back up

    assert len(alerts) == 1
    assert alerts[0].startswith("[BACK UP]")


def test_slow_target_is_flagged_but_still_up(live_server, monkeypatch):
    from uptime import check
    monkeypatch.setattr(check, "SLOW_SECONDS", -1.0)   # everything is "slow"
    # check_once lives in check.py; monitor imported the function, not the module
    import uptime.monitor as m
    monkeypatch.setattr(m, "is_slow", lambda _r: True)

    lines = []
    state, alerts = m.run_round(config_for(live_server), {}, lines.append)

    assert state == {"local": "up"}
    assert alerts == []
    assert any("(slow)" in line for line in lines)


def test_state_is_persisted_and_reloaded(tmp_path, live_server):
    """A restart must not re-alert a target that is already down."""
    state_file = tmp_path / "state.json"

    # The default argument is bound when the function is defined, so patching
    # the module attribute would not change it; pass the path instead.
    monitor.save_state({"local": "down"}, state_file)
    assert json.loads(state_file.read_text()) == {"local": "down"}
    assert monitor.load_state(state_file) == {"local": "down"}

    # The reloaded state means a still-down target is not alerted again.
    lines = []
    state, alerts = monitor.run_round(config_for("http://127.0.0.1:1/"),
                                      monitor.load_state(state_file), lines.append)
    assert state == {"local": "down"}
    assert alerts == []           # it was already known to be down


# --- config validation -----------------------------------------------------

def test_missing_targets_key_is_rejected():
    with pytest.raises(ValueError, match="'targets' list"):
        validate({"interval": 5})


def test_empty_targets_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        validate({"targets": []})


def test_target_without_url_is_rejected():
    with pytest.raises(ValueError, match="needs 'name' and 'url'"):
        validate({"targets": [{"name": "x"}]})


def test_valid_config_passes():
    validate({"targets": [{"name": "x", "url": "https://x.test"}]})


def test_interval_defaults_and_never_goes_below_one():
    assert interval_of({}) == 30
    assert interval_of({"interval": 0}) == 1      # a hot loop is never useful
    assert interval_of({"interval": -5}) == 1
    assert interval_of({"interval": 7}) == 7