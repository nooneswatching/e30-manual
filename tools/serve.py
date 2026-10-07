#!/usr/bin/env python3
"""Serve the site/ folder locally (the app fetches JSON, so it needs http://, not file://)."""
import http.server
import os
import sys
from pathlib import Path

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
os.chdir(Path(__file__).resolve().parent.parent / "site")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webp": "image/webp", ".json": "application/json"}


print(f"Serving http://localhost:{port}/  (Ctrl-C to stop)")
http.server.ThreadingHTTPServer(("", port), Handler).serve_forever()
