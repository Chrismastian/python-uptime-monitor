"""Demo: run real rounds against a local service that dies and comes back.

Shows the alerting rule doing its job: a transition produces exactly one
message, and repeated checks in the same state stay silent.
"""

import http.server
import threading
import time
from pathlib import Path

from uptime import monitor
from uptime.config import load_config

STATE_FILE = Path("demo_state.json")
CONFIG = Path("demo_targets.json")


class Service(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def start_service():
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Service)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def write_config(port: int) -> None:
    CONFIG.write_text(
        '{\n  "interval": 1,\n  "targets": [\n'
        f'    {{"name": "local-service", "url": "http://127.0.0.1:{port}/"}}\n'
        "  ]\n}\n",
        encoding="utf-8",
    )


def main() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()

    httpd, port = start_service()
    write_config(port)
    config = load_config(CONFIG)

    state = {}

    def round_with_label(label: str) -> None:
        print(f"\n=== {label} ===")
        # run_round returns (state, alerts); keep the state and persist it,
        # because carrying it between rounds is what silences repeat alerts.
        new_state, _alerts = monitor.run_round(
            config, monitor.load_state(STATE_FILE), print
        )
        state.update(new_state)
        monitor.save_state(state, STATE_FILE)

    round_with_label("round 1: service alive")
    round_with_label("round 2: still alive (expect no alert)")

    print("\n>>> stopping the service <<<")
    httpd.shutdown()
    httpd.server_close()
    time.sleep(0.5)

    round_with_label("round 3: service is DOWN (expect 1 alert)")
    round_with_label("round 4: still down (expect NO alert)")

    print("\n>>> starting the service again <<<")
    httpd2, port2 = start_service()
    write_config(port2)
    config = load_config(CONFIG)

    round_with_label("round 5: service is BACK (expect 1 alert)")
    round_with_label("round 6: still alive (expect no alert)")

    httpd2.shutdown()
    httpd2.server_close()
    print("\nSaved state:", monitor.load_state(STATE_FILE))


if __name__ == "__main__":
    main()