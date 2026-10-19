# python-uptime-monitor

[![CI](https://github.com/Chrismastian/python-uptime-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/Chrismastian/python-uptime-monitor/actions/workflows/ci.yml)

A small uptime monitor: it reads its targets from a config file, checks them on
a schedule, and sends an alert **only when a target changes state**.

The alerting rule is the point of the repo. A service that dies at midnight and
recovers at 8am is checked 960 times at a 30-second interval. Alerting on every
failed check would send 960 messages and train you to ignore them. This monitor
sends two: one when it goes down, one when it comes back.

## Usage

```bash
python -m uptime.cli --init              # write a starter targets.json
python -m uptime.cli --rounds 3          # three rounds, then stop
python -m uptime.cli                     # run forever (Ctrl+C to stop)
python -m uptime.cli --interval 10       # override the interval in the config
```

`targets.json`:

```json
{
  "interval": 30,
  "targets": [
    {"name": "example", "url": "https://example.com"},
    {"name": "api", "url": "https://example.com/api"}
  ]
}
```

Adding a target is a config edit, not a code change.

## The alerting rule

State per target is one of `up` / `down`, plus "never checked" before the first
look. There are two cases:

- **First check**: alert only if the result is `down`. A target that was
  already dead when monitoring started should still be reported; a healthy one
  needs no "everything is fine" message.
- **Every check after that**: alert only when the state *changes*. Repeated
  failures are silent, which is what collapses a long outage into one message.

Seen from a real run against a local service that is stopped and restarted:

```
=== round 1: service alive ===
     OK   local-service 200 in 969 ms
=== round 2: still alive ===
     OK   local-service 200 in 3 ms
>>> stopping the service <<<
=== round 3: service is DOWN ===
[DOWN] local-service: connection refused after 2038 ms      <- one alert
=== round 4: still down ===
     DOWN local-service connection refused after 2043 ms    <- silent
>>> starting the service again <<<
=== round 5: service is BACK ===
[BACK UP] local-service: 200 in 3 ms                        <- one alert
=== round 6: still alive ===
     OK   local-service 200 in 4 ms
```

Six rounds, two alerts. Without the rule it would have been six messages.

## Why the state is persisted

`state.json` holds the last known state of each target:

```json
{"local-service": "up"}
```

Without it, every restart would treat each target as "never checked" and
re-alert anything that is currently down. With it, a restart is silent.

## Layout

- **`uptime/check.py`** — `check_once` (the network call), `decide` (the
  transition rule), `describe` / `summary` (report lines), `is_slow`.
  `decide` is pure, so the alert logic is tested without any network.
- **`uptime/config.py`** — reads and validates `targets.json`. A missing file
  is an error rather than an empty default: a monitor with no targets has
  nothing to do. `interval_of` clamps to a minimum of 1 second, because a zero
  interval would spin with no pause.
- **`uptime/monitor.py`** — `run_round` (check every target once) and
  `run_monitor` (the schedule: poll, sleep, repeat). The notifier and the sleep
  function are injected, so tests run without printing or waiting.
- **`uptime/cli.py`** — argument parsing and `--init`.

## Tests

```bash
pip install pytest
pytest
```

27 tests: state mapping, the first-check rule, every transition (`up→down`,
`down→up`, unchanged states), a long outage producing exactly one alert, an
outage-plus-recovery producing exactly two, report formatting, slow detection,
state persistence across a simulated restart, and config validation. The
round-level tests run against a real local HTTP server — no internet, no
sleeping.

## Notes and limits

- `HTTPError` (a 404 or 500) counts as **down**: the connection worked but the
  service is not healthy. If you would rather treat a 404 as up, that is a
  deliberate policy choice to make in `decide`.
- Alerts go to stdout. Wiring them to email, Slack or Telegram means replacing
  the `notifier` argument — the logic does not change.
- Checks are sequential, so one slow target delays the others. Concurrency is
  the next step, not a current feature.
- State lives in a JSON file: fine for one monitor process, not for several
  running at once.