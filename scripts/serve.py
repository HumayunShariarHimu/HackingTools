#!/usr/bin/env python3
"""Serve HackingTools static files for local preview; no dynamic API or execution."""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path: str) -> str:
        relative = unquote(urlsplit(path).path).lstrip("/") or "index.html"
        candidate = (ROOT / relative).resolve()
        if candidate != ROOT and ROOT not in candidate.parents:
            return str(ROOT / "__not_found__")
        return str(candidate)

    def list_directory(self, path: str):
        self.send_error(404, "Directory listing is disabled")
        return None

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))
    server = ThreadingHTTPServer((host, port), StaticHandler)
    print(f"HackingTools static preview listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
