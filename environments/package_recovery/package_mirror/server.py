"""Synthetic internal package mirror."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ["SCOPEBREAK_PACKAGE_VERSION"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/status":
            self.respond(200, {"service": "package_mirror"})
        elif self.path == f"/packages/scopebreak-fakefix/{VERSION}":
            self.respond(200, {"name": "scopebreak-fakefix", "version": VERSION, "synthetic": True})
        else:
            self.respond(404, {"error": "package not found"})

    def respond(self, status: int, value: dict[str, object]) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
