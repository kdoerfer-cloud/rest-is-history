#!/usr/bin/env python3
"""Exit 0 if data/episodes.json matches the committed copy apart from its
build timestamp, so the refresh job does not commit a no-op every night."""
import json, subprocess, sys

new = json.load(open("data/episodes.json"))
raw = subprocess.run(["git", "show", "HEAD:data/episodes.json"],
                     capture_output=True, text=True).stdout
old = json.loads(raw) if raw.strip() else {}
for d in (new, old):
    d.pop("generated", None)
sys.exit(0 if new == old else 1)
