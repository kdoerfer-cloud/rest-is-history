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
import argparse, base64, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, getpass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = (Path.home() / "Library/Group Containers/243LU875E5.groups.com.apple.podcasts"
      / "Documents/MTLibrary.sqlite")
ITERATIONS = 200_000
CORE_DATA_EPOCH = 978_307_200          # 2001-01-01 in Unix seconds


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
    if not DB.exists():
        sys.exit(f"Podcasts database not found at:\n  {DB}\n"
                 "Open the Podcasts app on this Mac at least once, then try again.")
    # the app keeps the database open, so work on a copy
    tmp = Path(tempfile.gettempdir()) / "rih-podcasts-snapshot.sqlite"
    shutil.copy2(DB, tmp)
    con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT e.ZFREEENCLOSUREURL AS url, e.ZPLAYSTATE AS state, e.ZPLAYCOUNT AS plays,
               e.ZPLAYHEAD AS head, e.ZDURATION AS dur, e.ZLASTDATEPLAYED AS played
        FROM ZMTEPISODE e
        JOIN ZMTPODCAST p ON p.Z_PK = e.ZPODCAST
        WHERE p.ZTITLE LIKE '%Rest Is History%'
    """).fetchall()
    con.close()
    tmp.unlink(missing_ok=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="commit and push data/listened.json")
    ap.add_argument("--plain", action="store_true", help="write it unencrypted")
    args = ap.parse_args()

    episodes = json.loads((ROOT / "data" / "episodes.json").read_text())["episodes"]
    by_asset = {glt(e["au"]): e["k"] for e in episodes if glt(e["au"])}

    listened, matched, skipped = {}, 0, 0
    for r in read_play_state():
        key = by_asset.get(glt(r["url"]))
        if not key:
            skipped += 1                      # Club/bonus episodes, absent from the public feed
            continue
        matched += 1
        dur, head = r["dur"] or 0, r["head"] or 0
        if (r["state"] == 2) or (r["plays"] or 0) > 0 or (dur and head >= dur * 0.95):
            when = r["played"]
            listened[key] = int((CORE_DATA_EPOCH + when) * 1000) if when else 0

    payload = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "apple-podcasts", "listened": listened}
    out = ROOT / "data" / "listened.json"

    if args.plain:
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

    print(f"{len(listened)} listened, from {matched} episodes matched "
          f"({skipped} Club/bonus rows skipped) -> {out.relative_to(ROOT)}"
          f"{' (unencrypted)' if args.plain else ''}")

    if args.push:
        subprocess.run(["git", "-C", str(ROOT), "add", "data/listened.json"], check=True)
        done = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"])
        if done.returncode == 0:
            print("No change since the last export.")
            return
        subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m",
                        f"Update listening history — {len(listened)} episodes"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "pull", "--rebase", "-q"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "push", "-q"], check=True)
        print("Pushed.")


if __name__ == "__main__":
    main()
