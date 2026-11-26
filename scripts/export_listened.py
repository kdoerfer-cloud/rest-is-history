#!/usr/bin/env python3
"""
Export your Apple Podcasts listening history for The Rest Is History and publish it
with the site, encrypted.

    python3 scripts/export_listened.py                # encrypt and write data/listened.json
    python3 scripts/export_listened.py --push         # ...and commit and push it
    python3 scripts/export_listened.py --plain        # write it unencrypted (not advised)

Runs on the Mac, where the Podcasts app keeps its database. The repository is public,
so the file is encrypted here with AES-GCM under a key stretched from your passphrase
with PBKDF2-SHA256; the site asks for that passphrase once per browser and decrypts in
the page. The passphrase is never written to the repository.

Passphrase, in order of preference:
  1. the RIH_PASSPHRASE environment variable
  2. the macOS keychain:  security add-generic-password -a "$USER" -s rih-listened -w
  3. a prompt

Needs `cryptography` (one-off:  python3 -m pip install cryptography).
"""
import time, argparse, re, base64, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, getpass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = (Path.home() / "Library/Group Containers/243LU875E5.groups.com.apple.podcasts"
      / "Documents/MTLibrary.sqlite")
ITERATIONS = 200_000
CORE_DATA_EPOCH = 978_307_200          # 2001-01-01 in Unix seconds
# A play position shorter than this is treated as an accidental start, not a part-heard episode.
# Chosen from the positions on 2026-11-20 (18 unfinished episodes): three sat at 17-78 s, then
# nothing until 145 s. A judgment call on a small sample; re-check with --stats.
PARTIAL_MIN_SECONDS = 120



def glt(url):
    """The Megaphone asset id, which is what the feed and the app agree on."""
    m = re.search(r"/(GLT\d+)\.mp3", (url or "").split("?")[0])
    return m.group(1) if m else None


def passphrase():
    if os.environ.get("RIH_PASSPHRASE"):
        return os.environ["RIH_PASSPHRASE"]
    try:
        out = subprocess.run(["security", "find-generic-password",
                              "-a", os.environ.get("USER", ""), "-s", "rih-listened", "-w"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return getpass.getpass("Passphrase for the published listening history: ")


def read_play_state():
    """Read every Rest Is History episode row from the Podcasts database.

    Apple renames columns between macOS releases, so this looks at what the database
    actually has instead of assuming fixed names, and returns plain dicts.
    """
    if not DB.exists():
        sys.exit(f"Podcasts database not found at:\n  {DB}\n"
                 "Open the Podcasts app on this Mac at least once, then try again.")
    # the app keeps the database open, so work on a copy
    tmp = Path(tempfile.gettempdir()) / "rih-podcasts-snapshot.sqlite"
    shutil.copy2(DB, tmp)
    for ext in ("-wal", "-shm"):                       # pick up uncommitted plays too
        side = Path(str(DB) + ext)
        if side.exists():
            shutil.copy2(side, Path(str(tmp) + ext))
    con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    def cols(table):
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    ec, pc = cols("ZMTEPISODE"), cols("ZMTPODCAST")

    def pick(names, have=ec):
        return [n for n in names if n in have]

    url_cols = pick(["ZFREEENCLOSUREURL", "ZENCLOSUREURL", "ZASSETURL", "ZDOWNLOADURL",
                     "ZPLAYBACKURL", "ZWEBPAGEURL", "ZSTREAMURL"]) or \
               [c for c in ec if "URL" in c and "ARTWORK" not in c and "IMAGE" not in c]
    guid_cols = pick(["ZGUID", "ZUUID", "ZEPISODEGUID"])
    title_cols = pick(["ZTITLE", "ZCLEANEDTITLE", "ZITUNESTITLE"])
    state = {"state": pick(["ZPLAYSTATE", "ZPLAYSTATUS"]), "plays": pick(["ZPLAYCOUNT"]),
             "head": pick(["ZPLAYHEAD", "ZPLAYHEADPOSITION", "ZPLAYPOSITION"]),
             "dur": pick(["ZDURATION"]),
             "played": pick(["ZLASTDATEPLAYED", "ZLASTPLAYEDDATE", "ZPLAYSTATEMANUALLYSET"])}
    sel = [f"e.{c} AS u_{c}" for c in url_cols] + [f"e.{c} AS g_{c}" for c in guid_cols] + \
          [f"e.{c} AS t_{c}" for c in title_cols] + \
          [f"{('e.'+v[0]) if v else 'NULL'} AS {k}" for k, v in state.items()]
    if "ZPODCAST" in ec:
        join = "JOIN ZMTPODCAST p ON p.Z_PK = e.ZPODCAST"
    elif "ZPODCASTUUID" in ec and "ZUUID" in pc:
        join = "JOIN ZMTPODCAST p ON p.ZUUID = e.ZPODCASTUUID"
    else:
        sys.exit("Unrecognised Podcasts database layout. Episode columns: " + ", ".join(ec))
    ptitle = "p.ZTITLE" if "ZTITLE" in pc else "p.ZCLEANEDTITLE"
    try:
        rows = con.execute(f"SELECT {', '.join(sel)} FROM ZMTEPISODE e {join} "
                           f"WHERE {ptitle} LIKE '%Rest Is History%'").fetchall()
    except sqlite3.Error as err:
        sys.exit(f"Could not read the Podcasts database ({err}).\nEpisode columns: " + ", ".join(ec))
    con.close()
    for ext in ("", "-wal", "-shm"):
        Path(str(tmp) + ext).unlink(missing_ok=True)
    out = []
    for r in rows:
        d = dict(r)
        out.append({"urls": [d[k] for k in d if k.startswith("u_") and d[k]],
                    "guids": [d[k] for k in d if k.startswith("g_") and d[k]],
                    "titles": [d[k] for k in d if k.startswith("t_") and d[k]],
                    "state": d["state"], "plays": d["plays"], "head": d["head"],
                    "dur": d["dur"], "played": d["played"]})
    return out


def norm_title(t):
    t = re.sub(r"^\s*\d+[.:]\s*", "", str(t or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def print_stats(fracs):
    """Shape of the play positions, so the cut-offs are chosen from the data. Numbers only."""
    def pct(xs, q):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")
    for label, want in (("counted as listened", True), ("NOT counted as listened", False)):
        fr = [f for f, h, _ in fracs if h is want]
        secs = [s for _, h, s in fracs if h is want]
        print(f"--stats: {label}, with a play position: n={len(fr)}")
        if fr:
            print("   fraction played  p0/p10/p25/p50/p75/p90/p100: " +
                  " ".join(f"{pct(fr, q):.2f}" for q in (0, .10, .25, .50, .75, .90, .999)))
            print("   seconds in       p0/p10/p25/p50/p75/p90/p100: " +
                  " ".join(f"{pct(secs, q):.0f}" for q in (0, .10, .25, .50, .75, .90, .999)))
            edges = [0, .01, .05, .10, .25, .50, .75, .90, .95, 1.01, 99]
            print("   histogram of fraction played: " + "  ".join(
                f"[{a:.2f},{b:.2f})={sum(1 for f in fr if a <= f < b)}" for a, b in zip(edges, edges[1:])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="commit and push data/listened.json")
    ap.add_argument("--plain", action="store_true", help="write it unencrypted (the default)")
    ap.add_argument("--encrypt", action="store_true",
                    help="encrypt it with your passphrase (the page then has to be unlocked on each browser)")
    ap.add_argument("--stats", action="store_true",
                    help="print how far into each unfinished episode the play position is (no titles)")
    args = ap.parse_args()
    args.plain = not args.encrypt

    episodes = json.loads((ROOT / "data" / "episodes.json").read_text())["episodes"]
    by_asset = {glt(e["au"]): e["k"] for e in episodes if glt(e["au"])}
    feed_dur = {e["k"]: float(e.get("dur") or 0) for e in episodes}
    by_guid = {e["g"]: e["k"] for e in episodes if e.get("g")}
    by_title = {norm_title(e["ft"]): e["k"] for e in episodes}
    by_title.update({norm_title(e["t"]): e["k"] for e in episodes})

    # listened: episode key -> when it was played (ms; 0 when Podcasts holds no date)
    # partial:  episode key -> [seconds in, episode length in seconds, when (ms or 0)]
    #           for episodes started but not finished
    listened, partial, matched, skipped = {}, {}, 0, 0
    fracs = []                                # --stats: (fraction played, counted as listened)
    for r in read_play_state():
        key = None
        for u in r["urls"]:
            key = key or by_asset.get(glt(u))
        for g in r["guids"]:
            key = key or by_guid.get(g)
        for t in r["titles"]:
            key = key or by_title.get(norm_title(t))
        if not key:
            skipped += 1                      # Club/bonus episodes, absent from the public feed
            continue
        matched += 1
        # Podcasts often holds no length (it was 0 for every row on 2026-11-20), so fall back
        # on the length in the feed. Without it the 95% rule below can never fire.
        dur, head = r["dur"] or feed_dur.get(key, 0), r["head"] or 0
        when = r["played"]
        when = int((CORE_DATA_EPOCH + when) * 1000) if when else 0
        heard = (r["state"] == 2) or (r["plays"] or 0) > 0 or (dur and head >= dur * 0.95)
        if dur and head > 0:
            fracs.append((head / dur, bool(heard), head))
        if heard:
            listened[key] = when
            partial.pop(key, None)
        elif (head >= PARTIAL_MIN_SECONDS and key not in listened
              and head > partial.get(key, [0])[0]):       # several rows can match one episode
            partial[key] = [int(head), int(dur), when]

    if args.stats:
        print_stats(fracs)

    payload = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "apple-podcasts", "listened": listened, "partial": partial}
    out = ROOT / "data" / "listened.json"

    if args.plain:
        try:                                   # nothing new to publish: leave the file alone
            old = json.loads(out.read_text())
            if (not old.get("ct") and old.get("listened") == listened
                    and old.get("partial", {}) == {k: list(v) for k, v in partial.items()}):
                print(f"{len(listened)} listened, unchanged since {old.get('generated', '?')[:10]}.")
                if args.push:
                    push_pending()             # an earlier night's commit may still be waiting
                return
        except Exception:
            pass
        out.write_text(json.dumps(payload, separators=(",", ":")))
    else:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
        except ImportError:
            sys.exit("This needs the 'cryptography' package:\n"
                     "  python3 -m pip install cryptography\n"
                     "(or run with --plain to publish it unencrypted)")
        salt, iv = os.urandom(16), os.urandom(12)
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=ITERATIONS).derive(passphrase().encode())
        ct = AESGCM(key).encrypt(iv, json.dumps(payload, separators=(",", ":")).encode(), None)
        out.write_text(json.dumps({
            "v": 1, "kdf": "PBKDF2-SHA256", "iter": ITERATIONS,
            "salt": base64.b64encode(salt).decode(),
            "iv": base64.b64encode(iv).decode(),
            "ct": base64.b64encode(ct).decode(),
            "generated": payload["generated"], "count": len(listened),
        }, separators=(",", ":")))

    print(f"{len(listened)} listened, {len(partial)} part-heard, from {matched} episodes matched "
          f"({skipped} Club/bonus rows skipped) -> {out.relative_to(ROOT)}"
          f"{' (unencrypted)' if args.plain else ''}")

    if args.push:
        subprocess.run(["git", "-C", str(ROOT), "add", "data/listened.json"], check=True)
        done = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"])
        if done.returncode == 0:
            print("No change since the last export.")
        else:
            subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m",
                            f"Update listening history — {len(listened)} episodes"], check=True)
        push_pending()


def push_pending():
    """Send any local commits GitHub does not have yet, retrying a failed push.
    On 2026-11-23 a push failed once and, because later nights found nothing new and
    stopped before pushing, the commit sat on this Mac for three days."""
    git = ["git", "-C", str(ROOT)]
    for attempt in (1, 2, 3):
        subprocess.run(git + ["fetch", "-q"])
        ahead = subprocess.run(git + ["rev-list", "--count", "@{u}..HEAD"],
                               capture_output=True, text=True).stdout.strip()
        if ahead in ("", "0"):
            print("Nothing waiting to push." if attempt == 1 else "Pushed.")
            return
        print(f"{ahead} commit(s) to push (attempt {attempt}).")
        if (subprocess.run(git + ["pull", "--rebase", "-q"]).returncode == 0
                and subprocess.run(git + ["push", "-q"]).returncode == 0):
            print("Pushed.")
            return
        time.sleep(20 * attempt)
    sys.exit("Could not push to GitHub after three attempts; the commit is kept and the next run will try again.")


if __name__ == "__main__":
    main()
