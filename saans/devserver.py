"""Local dashboard + API on http://localhost:8000, using the same handlers as Lambda.

    python -m saans.devserver

Worker invocations run in a background thread instead of an async Lambda invoke.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import lambdas
from .config import load_env

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
API_PATHS = {"/schools", "/status", "/run-now", "/telegram"}


def _invoke_in_thread(payload: dict) -> None:
    threading.Thread(target=lambdas.worker_handler, args=(payload, None), daemon=True).start()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _api(self, method: str) -> bool:
        url = urllib.parse.urlsplit(self.path)
        if url.path not in API_PATHS:
            return False
        length = int(self.headers.get("Content-Length") or 0)
        event = {
            "routeKey": f"{method} {url.path}",
            "queryStringParameters": dict(urllib.parse.parse_qsl(url.query)) or None,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": self.rfile.read(length).decode() if length else None,
        }
        resp = lambdas.api_handler(event, None)
        body = resp["body"].encode()
        self.send_response(resp["statusCode"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def do_GET(self):
        if not self._api("GET"):
            super().do_GET()

    def do_POST(self):
        if not self._api("POST"):
            self.send_error(404)


def main(port: int = 8000) -> None:
    load_env()
    logging.basicConfig(level=logging.INFO)
    lambdas.invoke_worker = _invoke_in_thread
    print(f"SaansSaathi dashboard on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
