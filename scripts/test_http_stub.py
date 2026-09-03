"""
Minimal local HTTP stub for testing interop's http_filesystem adapter.

GET  /<name>  -> returns bytes previously PUT under that name (404 if absent)
PUT  /<name>  -> stores the request body under that name

Usage:
    python test_http_stub.py [port]   # default port 8000

Storage is in-memory for GET/PUT round-trips within one server run — good
enough to prove open_read/open_write/read_bytes/write_bytes actually work
end-to-end without needing real cloud infrastructure.
"""

import contextlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_STORE: dict[str, bytes] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        data = _STORE.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_PUT(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        _STORE[self.path] = body
        print(f"PUT {self.path} ({len(body)} bytes)")
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        # Quieter default logging; keep PUT confirmations only.
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving on http://127.0.0.1:{port} (Ctrl-C to stop)")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
