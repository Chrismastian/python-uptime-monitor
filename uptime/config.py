"""Read the list of targets from a JSON file. Same file-I/O shape as the
earlier CLI repos, except the contents are configuration rather than data the
user accumulates.
"""

import json
from pathlib import Path

CONFIG_FILE = Path("targets.json")

# Expected shape:
# {
#   "interval": 30,
#   "targets": [
#     {"name": "example", "url": "https://example.com"},
#     {"name": "api", "url": "https://example.com/api"}
#   ]
# }


def load_config(path: Path = CONFIG_FILE) -> dict:
    """Read the monitor configuration. Raise FileNotFoundError if absent."""
    # Unlike the todo repo, a missing file is NOT turned into an empty
    # default: a monitor with no targets has nothing to do, so failing loudly
    # beats silently doing nothing.
    raw = json.loads(path.read_text("utf-8"))
    validate(raw)
    return raw


def validate(config: dict) -> None:
    """Raise ValueError when the config is not usable."""
    # This is a trust boundary: the file is edited by hand, so it is checked.
    if not isinstance(config.get("targets"), list):
        raise ValueError("config must have a 'targets' list")

    if not config["targets"]:
        raise ValueError("'targets' must contain at least one target")

    for target in config["targets"]:
        if not target.get("name") or not target.get("url"):
            raise ValueError(f"every target needs 'name' and 'url': {target!r}")


def interval_of(config: dict) -> int:
    """Seconds between rounds. Default 30, never below 1 to avoid a hot loop."""
    # A zero or negative interval would spin with no pause, burning CPU and
    # hammering the targets, so it is clamped rather than honoured.
    return max(1, int(config.get("interval", 30)))


def set_interval(config: dict, interval: int) -> dict:
    """Return a copy of the config with a new interval."""
    return {**config, "interval": interval}


def save_config(config: dict, path: Path = CONFIG_FILE) -> None:
    """Write the config back to disk."""
    path.write_text(json.dumps(config, indent=2), "utf-8")


def write_example(path: Path = CONFIG_FILE) -> None:
    """Write a starter configuration file."""
    example = {
        "interval": 30,
        "targets": [
            {"name": "example", "url": "https://example.com"},
            {"name": "httpbin", "url": "https://httpbin.org/status/200"},
        ],
    }
    save_config(example, path)