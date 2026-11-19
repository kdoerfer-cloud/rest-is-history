"""
Listening-order metadata for the "Journeys" view.

For every episode this adds:
  rk  run key      - episodes that are consecutive parts of one story share a run
  ro  run order    - position inside the run (part order, not release order)
  sq  sequence yr  - where the episode sits in a historical listening order
  jk  kind         - "s" narrative spine, "o" overview / thematic, "x" special / extra

A run is a series' consecutive parts (it restarts when the part number goes back to 1,
so Nelson's two five/six-part runs, or the two halves of the Hundred Years' War, are
separate runs). Runs stay together and sit at the median start year of their episodes.
A "survey" run (several parts marching through more than 250 years - Ireland, Portugal,
Baghdad ...) is spread out instead: each part sits at its own start year.

Anything very long-spanning that is not a narrative (a nation's whole history in one
episode, a thematic romp like Smuggling) is an overview. Christmas specials and other
format episodes are specials. data/sequence.json holds the hand corrections.
"""
import json, re, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERVIEW_SPAN = 150      # a single episode spanning more than this is an overview, not a narrative
SURVEY_SPAN = 250        # a multi-part run marching through more than this is a "survey" run
SPECIAL_STRANDS = {"Christmas Specials & Podcast Formats"}

def part_no(title):
    m = (re.search(r"\(Part (\d+)\)", title, re.I) or re.search(r"\bpart (\d+)\s*$", title, re.I)
         or re.search(r"\bPart (\d+)\b", title))
    return int(m.group(1)) if m else None

def load_cfg():
    p = ROOT / "data" / "sequence.json"
    return json.loads(p.read_text()) if p.exists() else {}

def add_sequence(episodes):
    cfg = load_cfg()
    force_o = set(cfg.get("overview", []))
    force_s = set(cfg.get("spine", []))
    force_sq = cfg.get("sq", {})
    survey_force = set(cfg.get("survey_series", []))
    by_series = {}
    for e in episodes:
        by_series.setdefault(e["s"], []).append(e)

    # --- runs
    for s, L in by_series.items():
        L.sort(key=lambda e: (e["d"] or "", int(e["n"] or 0)))
        runs, cur, last = [], [], None
        for e in L:
            p = part_no(e["ft"])
            if p is None:
                # un-numbered episodes released back to back (consecutive episode numbers,
                # a fortnight or less apart) are one run, in release order
                prev = L[L.index(e) - 1] if L.index(e) else None
                joined = (prev is not None and part_no(prev["ft"]) is None and prev["n"] and e["n"]
                          and int(e["n"]) == int(prev["n"]) + 1 and cur and cur[-1] is prev)
                if not joined and cur: runs.append(cur); cur = []
                cur.append(e); last = None; continue
            if cur and (last is None or p <= last):
                runs.append(cur); cur = []
            cur.append(e); last = p
        if cur: runs.append(cur)
        for i, run in enumerate(runs):
            run.sort(key=lambda e: (part_no(e["ft"]) or 0, e["d"] or ""))
            span = max(e["y1"] for e in run) - min(e["y0"] for e in run)
            increasing = all(b["y0"] >= a["y0"] for a, b in zip(run, run[1:]))
            survey = len(run) > 1 and ((span > SURVEY_SPAN and increasing) or s in survey_force)
            for e in run:
                w = (e["y1"] or 0) - (e["y0"] or 0)
                if e["k"] in force_s: e["jk"] = "s"
                elif e["k"] in force_o: e["jk"] = "o"
                elif e["st"] in SPECIAL_STRANDS: e["jk"] = "x"
                elif survey: e["jk"] = "s"
                else: e["jk"] = "o" if w > OVERVIEW_SPAN else "s"
            ys = [e["y0"] for e in run if e["jk"] == "s"] or [e["y0"] for e in run]
            med = int(statistics.median_low(ys))
            for j, e in enumerate(run):
                e["rk"] = f"{s}#{i+1}"
                e["ro"] = j + 1
                e["pt"] = part_no(e["ft"])
                e["_r0"] = min(x["y0"] for x in run)
                e["sq"] = e["y0"] if survey else med
                if e["k"] in force_sq: e["sq"] = force_sq[e["k"]]
    # one global listening order; the page sorts any subset (a region, a nation) by "jx"
    kind_rank = {"s": 0, "o": 1, "x": 2}
    order = sorted(episodes, key=lambda e: (kind_rank[e["jk"]], e["sq"], e["_r0"], e["rk"], e["ro"]))
    for i, e in enumerate(order):
        e["jx"] = i
    for e in episodes:
        e.pop("_r0", None)
    return episodes
