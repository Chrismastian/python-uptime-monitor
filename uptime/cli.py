"""Command line entry point: `python -m uptime.cli --rounds 3`."""

import argparse
from pathlib import Path

from .config import CONFIG_FILE, load_config, save_config, set_interval, write_example
from .monitor import run_monitor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uptime-monitor")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE,
                        help="path to the targets file (default: targets.json)")
    parser.add_argument("--rounds", type=int, default=None,
                        help="stop after N rounds (default: run forever)")
    parser.add_argument("--interval", type=int, default=None,
                        help="seconds between rounds, overriding the config")
    parser.add_argument("--init", action="store_true",
                        help="write an example targets file and exit")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    # --init writes a starter file and stops: setup, not monitoring.
    if args.init:
        write_example(args.config)
        print(f"wrote example config to {args.config}")
        return

    # --interval rewrites the file so the config stays the single source of
    # truth for the interval, rather than an option that only applies once.
    if args.interval is not None:
        save_config(set_interval(load_config(args.config), args.interval), args.config)

    run_monitor(args.config, rounds=args.rounds)


if __name__ == "__main__":
    main()