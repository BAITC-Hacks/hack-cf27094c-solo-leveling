"""Dependency-free local web app. Run: python app.py"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from catalog import options
from matcher import InvalidQuery, recommend


INDEX = (Path(__file__).parent / "static" / "index.html").read_bytes()


class Handler(BaseHTTPRequestHandler):
    def respond(self, code: int, content: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(content)

    def json_response(self, code: int, payload: dict) -> None:
        self.respond(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        if route.path == "/":
            self.respond(200, INDEX, "text/html; charset=utf-8")
        elif route.path == "/api/options":
            self.json_response(200, options())
        elif route.path == "/api/recommend":
            params = {key: values[0] for key, values in parse_qs(route.query, keep_blank_values=True).items()}
            try:
                self.json_response(200, recommend(params))
            except InvalidQuery as error:
                self.json_response(400, {"error": str(error)})
        else:
            self.json_response(404, {"error": "Страница не найдена"})


def main() -> None:
    parser = argparse.ArgumentParser(description="HackAlem AI contractor matching MVP")
    # Cloud hosts provide PORT; local runs remain restricted to this computer.
    parser.add_argument("--host", default="0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Откройте http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
