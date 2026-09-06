#!/usr/bin/env python3
"""
Build data/episodes.json for the Rest Is History episode database.

  python3 scripts/build_data.py            # fetch the live RSS feed
  python3 scripts/build_data.py feed.xml   # build from a local copy

Historical classification (era / theme / region / dates / series / strand) lives in
data/classifications.json, keyed by a stable episode key. Episodes that appear in the
feed without a classification are carried through as "Unsorted" unless their series
name matches an already-classified series, in which case they inherit it.
"""
import json, re, sys, html, urllib.request, datetime
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
FEED = "https://feeds.megaphone.fm/GLT4787413333"
APPLE_ID = "1537788786"
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
      "content": "http://purl.org/rss/1.0/modules/content/"}

ERA_ORDER = [
    "Prehistory & the Ancient Near East", "The Ancient Greek World", "Ancient Rome",
    "The Early Middle Ages", "The High & Late Middle Ages", "Renaissance & Reformation",
    "Empires & Enlightenment", "Revolution & Napoleon", "The Long Nineteenth Century",
    "World Wars & the Interwar Years", "Cold War & Post-War World", "The Modern World",
    "Across the Ages", "Unsorted",
]
ERA_RANGE = {
    "Prehistory & the Ancient Near East": "before 800 BC", "The Ancient Greek World": "800–146 BC",
    "Ancient Rome": "753 BC – AD 476", "The Early Middle Ages": "476–1000",
    "The High & Late Middle Ages": "1000–1450", "Renaissance & Reformation": "1450–1600",
    "Empires & Enlightenment": "1600–1789", "Revolution & Napoleon": "1789–1815",
    "The Long Nineteenth Century": "1815–1914", "World Wars & the Interwar Years": "1914–1945",
    "Cold War & Post-War World": "1945–1991", "The Modern World": "1991–now",
    "Across the Ages": "many periods", "Unsorted": "not yet classified",
}
STRAND_ORDER = [
    "Origins & the Ancient Near East", "Egypt & the Pharaohs", "Greek Myth & the Age of Heroes",
    "Greece, Persia & Alexander", "The Roman Republic", "The Roman Empire & Its Fall",
    "Jesus, Saints & the Rise of Christianity", "After Rome: Byzantium & the Barbarians",
    "Islam, the Caliphates & the Crusades", "The Viking Age",
    "Medieval England: Conquest to Bosworth", "Medieval Europe: Church, Heresy & Plague",
    "Empires of Asia", "The Renaissance", "Explorers, Conquest & the New World",
    "Reformation & Religious War", "Tudors, Stuarts & the British Civil Wars",
    "Slavery & the Atlantic World", "Enlightenment & the Age of Reason",
    "The American Revolution & the Young Republic", "The French Revolution",
    "Napoleon & His Wars", "The British Empire", "Victorian Britain & the Industrial Age",
    "Civil War & the American Frontier", "Latin America: Revolution & Republic",
    "Science, Medicine & Invention", "The Road to the Great War & the First World War",
    "Russia: Revolution to Putin", "The Interwar Years & the Rise of Fascism",
    "The Second World War", "The Holocaust", "The Cold War & the Nuclear Age",
    "The End of Empire & the Postcolonial World", "America in the Sixties & After",
    "Modern Britain & Ireland", "The Modern Middle East", "Sport, Games & the World Cup",
    "Music, Film & Popular Culture", "Myths, Monsters & Mysteries", "Food, Drink & Daily Life",
    "Christmas Specials & Podcast Formats", "Unsorted",
]

def clean(s):
    if not s: return ""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p\s*>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace(" ", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()

PROMO = ["*The Rest Is History LIVE", "_______", "Twitter:", "Producer:",
         "Assistant Producer", "Join The Rest Is History Club", "Hosted on Acast",
         "Sign up to the newsletter"]

def trim_promo(desc):
    cut = len(desc)
    for m in PROMO:
        p = desc.find(m)
        if 0 < p < cut: cut = p
    return desc[:cut].strip()

def slug(t):
    return re.sub(r"\s+", "-", re.sub(r"[^a-z0-9]+", " ", t.lower()).strip())

def stable_key(num, full_title):
    return ("n" + num) if num else ("t" + slug(full_title))

def parse_title(raw_title):
    t = re.sub(r"\s+", " ", (raw_title or "").strip())
    m = re.match(r"^(\d{1,4})\s*[.:]\s*(.*)$", t)
    return (m.group(1), m.group(2).strip()) if m else (None, t)

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "rih-episode-db/2.0"})
    return urllib.request.urlopen(req, timeout=timeout).read()

def apple_links():
    """Map normalised episode title -> Apple Podcasts URL (most recent ~200 episodes)."""
    try:
        data = json.loads(get(f"https://itunes.apple.com/lookup?id={APPLE_ID}"
                              f"&entity=podcastEpisode&limit=200"))
    except Exception as exc:                                    # network hiccup: skip
        print(f"apple lookup failed: {exc}", file=sys.stderr)
        return {}
    out = {}
    for r in data.get("results", []):
        if r.get("wrapperType") != "podcastEpisode": continue
        tid, name = r.get("trackId"), r.get("trackName")
        if tid and name:
            out[slug(name)] = (f"https://podcasts.apple.com/us/podcast/"
                               f"{slug(name)[:60]}/id{APPLE_ID}?i={tid}")
    return out

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    xml = Path(src).read_bytes() if src else get(FEED)
    channel = ET.fromstring(xml).find("channel")

    cls_path = ROOT / "data" / "classifications.json"
    cls = json.loads(cls_path.read_text()) if cls_path.exists() else {}
    by_series = {}
    for c in cls.values():
        by_series.setdefault(c.get("series"), c)

    apple = apple_links()
    episodes, unsorted_titles = [], []

    for item in channel.findall("item"):
        full = re.sub(r"\s+", " ", (item.findtext("title") or "").strip())
        num, short = parse_title(full)
        key = stable_key(num, full)
        desc = trim_promo(clean(item.findtext("content:encoded", namespaces=NS)
                                or item.findtext("description")))
        enc, img = item.find("enclosure"), item.find("itunes:image", NS)
        pub = (item.findtext("pubDate") or "").strip()
        try:
            dt = datetime.datetime.strptime(pub[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            dt = None

        c = cls.get(key)
        if c is None:                                # new episode since last classification
            guess = short.split(":")[0].strip()
            c = by_series.get(guess)
            if c is not None:
                c = dict(c, subject="", confidence="inherited")
            else:
                c = {"start": dt.year if dt else 2026, "end": dt.year if dt else 2026,
                     "era": "Unsorted", "theme": "Everyday Life & Society",
                     "theme2": None, "region": "Global", "series": guess or short,
                     "strand": "Unsorted", "subject": "", "confidence": "unclassified"}
                unsorted_titles.append(full)

        link = c.get("apple") or apple.get(slug(short)) or ""
        guid = (item.findtext("guid") or "").strip()
        episodes.append({
            "k": key, "g": guid, "n": num, "t": short, "ft": full,
            "d": dt.strftime("%Y-%m-%d") if dt else "",
            "dur": int(item.findtext("itunes:duration", default="0", namespaces=NS) or 0),
            "ty": (item.findtext("itunes:episodeType", default="full", namespaces=NS) or "full"),
            "desc": desc,
            "au": (enc.get("url") if enc is not None else ""),
            "img": (img.get("href") if img is not None else ""),
            "ap": link,
            "s": c["series"], "st": c["strand"], "e": c["era"],
            "th": [t for t in (c.get("theme"), c.get("theme2")) if t],
            "r": c["region"], "y0": c["start"], "y1": c["end"],
            "sub": c.get("subject", ""), "cf": c.get("confidence", "medium"),
        })

    episodes.sort(key=lambda e: (e["d"] or "", e["n"] or ""), reverse=True)

    def tally(field):
        out = {}
        for e in episodes:
            vals = e[field] if isinstance(e[field], list) else [e[field]]
            for v in vals: out[v] = out.get(v, 0) + 1
        return out

    payload = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(episodes),
        "eras": [{"name": n, "range": ERA_RANGE.get(n, ""), "count": tally("e").get(n, 0)}
                 for n in ERA_ORDER if tally("e").get(n)],
        "strands": [{"name": n, "count": tally("st").get(n, 0)}
                    for n in STRAND_ORDER if tally("st").get(n)],
        "themes": sorted(tally("th").items(), key=lambda kv: -kv[1]),
        "regions": sorted(tally("r").items(), key=lambda kv: -kv[1]),
        "episodes": episodes,
    }
    out = ROOT / "data" / "episodes.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {out.relative_to(ROOT)}: {len(episodes)} episodes, "
          f"{len(payload['eras'])} eras, {len(payload['strands'])} strands")
    if unsorted_titles:
        print(f"{len(unsorted_titles)} unclassified episode(s):", file=sys.stderr)
        for t in unsorted_titles: print("  " + t, file=sys.stderr)

if __name__ == "__main__":
    main()
