#!/usr/bin/env python3
"""Fetch The Rest Is History RSS feed and emit raw episode records."""
import json, re, sys, html, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

FEED = "https://feeds.megaphone.fm/GLT4787413333"
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
      "content": "http://purl.org/rss/1.0/modules/content/"}

def clean(s):
    if not s: return ""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def parse_title(raw):
    t = re.sub(r"\s+", " ", (raw or "").strip())
    m = re.match(r"^(\d{1,4})\s*[.:]\s*(.*)$", t)
    if m:
        return m.group(1), m.group(2).strip()
    return None, t

def fetch(path=None):
    if path:
        xml = Path(path).read_bytes()
    else:
        req = urllib.request.Request(FEED, headers={"User-Agent": "rih-episode-db/1.0"})
        xml = urllib.request.urlopen(req, timeout=60).read()
    root = ET.fromstring(xml)
    ch = root.find("channel")
    out = []
    for it in ch.findall("item"):
        num, short = parse_title(it.findtext("title"))
        desc = clean(it.findtext("content:encoded", namespaces=NS) or it.findtext("description"))
        enc = it.find("enclosure")
        img = it.find("itunes:image", NS)
        out.append({
            "guid": (it.findtext("guid") or "").strip(),
            "num": num,
            "title": short,
            "fullTitle": re.sub(r"\s+", " ", (it.findtext("title") or "").strip()),
            "pubDate": (it.findtext("pubDate") or "").strip(),
            "duration": (it.findtext("itunes:duration", namespaces=NS) or "").strip(),
            "type": (it.findtext("itunes:episodeType", namespaces=NS) or "full").strip(),
            "desc": desc,
            "audio": (enc.get("url") if enc is not None else ""),
            "image": (img.get("href") if img is not None else ""),
        })
    return out

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else None
    eps = fetch(src)
    print(json.dumps(eps, ensure_ascii=False, indent=1))
    print(f"{len(eps)} episodes", file=sys.stderr)
