#!/usr/bin/env python3
"""Download the PDFs attached to the GitHub Release tagged "manuals" into manuals/.

    python tools/fetch_manuals.py nooneswatching/e30-manual
    GITHUB_TOKEN=ghp_... python tools/fetch_manuals.py nooneswatching/e30-manual   # private repo

The build workflow does the same automatically, so large scans never need to be committed.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

repo = sys.argv[1] if len(sys.argv) > 1 else "nooneswatching/e30-manual"
tag = sys.argv[2] if len(sys.argv) > 2 else "manuals"
dest = Path(__file__).resolve().parent.parent / "manuals"
dest.mkdir(exist_ok=True)
headers = {"Accept": "application/vnd.github+json", "User-Agent": "e30-manual"}
if os.environ.get("GITHUB_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]

req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=headers)
with urllib.request.urlopen(req) as r:
    release = json.load(r)
for asset in release.get("assets", []):
    name = asset["name"]
    if not name.lower().endswith((".pdf", ".json")):
        continue
    out = dest / name
    if out.exists() and out.stat().st_size == asset["size"]:
        print(f"{name}: already downloaded")
        continue
    print(f"{name}: {asset['size'] / 1e6:.0f} MB ...", flush=True)
    dl = urllib.request.Request(asset["url"], headers={**headers, "Accept": "application/octet-stream"})
    with urllib.request.urlopen(dl) as r, open(out, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
print("done ->", dest)
