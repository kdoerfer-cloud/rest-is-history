#!/usr/bin/env python3
"""Write preview.html — index.html with data/episodes.json inlined, so the page
works when opened directly from disk (no web server needed)."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
html = (ROOT / "index.html").read_text()
data = (ROOT / "data" / "episodes.json").read_text()
tag = '<script id="rih-data" type="application/json">' + data.replace("</", "<\\/") + "</script>\n<script>"
out = html.replace("<script>", tag, 1)
(ROOT / "preview.html").write_text(out)
print("wrote preview.html", len(out), "bytes")
