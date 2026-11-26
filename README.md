# The Rest Is History — Episode Database

A single-page, searchable database of every episode of *The Rest Is History*, organised by the
**history the episodes are about** rather than by the order they were released.

**Live site:** https://kdoerfer-cloud.github.io/rest-is-history/

## What it does

- **Timeline** — the whole catalogue laid out from the deepest past to the present. Each series
  sits at the date of the events it covers, grouped into 13 historical eras.
- **Story arcs** — 42 connected narrative arcs (*The Roman Republic*, *Reformation & Religious War*,
  *The Cold War & the Nuclear Age* …) in historical order, each holding its series and episodes.
- **Eras / Themes / Series** — the same catalogue sliced three other ways.
- **Sorting** — by historical date (earliest or latest first), release date, episode number,
  duration, or title.
- **Filtering** — listening status, era, theme, region, episode length, and a free historical
  year range (negative years are BC). Filters stack, and combine with full-text search across
  titles, subjects, series, arcs and descriptions.
- **Listening tracking** — mark episodes listened, favourite them, or queue them. *My listening*
  shows hours logged, progress per era, a list of episodes you stopped partway (with the time
  left), and a "pick up where you left off" list of part-finished series. Part-heard episodes
  carry a mark everywhere, and the filters include *Part-heard*. Your own marks are kept in your
  browser's local storage.
- **Download list** — the ⇣ button flags an episode to download; the *To download* filter and
  a list under *My listening* show them. The list can be shared across devices: it is saved to
  `data/downloads.json` in this repository through the GitHub API, using a GitHub key that each
  browser holds in its own storage (*My listening → Share the list across devices*). The key
  needs only *Contents: read and write* on this repository. Without a key a browser can read the
  shared list but not change it.
- **Bulk marking** — every group header has a `✓ all` toggle (whole series, story arc, era or
  theme at once), and whenever a filter or search is narrowing the list, the status line offers
  *Mark these N listened*.
- **Import from Apple Podcasts** — ⇅ Data → *Import from Apple Podcasts* takes a CSV of your
  Apple play state and marks everything you have already heard. Part-heard episodes go into your
  queue. See below.
- Light/dark theme (press <kbd>d</kbd>), keyboard search (<kbd>/</kbd>), and a mobile layout.

## How it's built

| Path | What it is |
| --- | --- |
| `index.html` | The whole site — no build step, no dependencies. Its only outside request is to the GitHub API, for the shared download list. |
| `data/episodes.json` | Generated. Every episode plus its classification. The page fetches this at load. |
| `data/classifications.json` | **Hand-curated.** The historical dating and grouping for each episode. |
| `scripts/build_data.py` | Merges the RSS feed with the classifications into `data/episodes.json`. |
| `scripts/fetch_feed.py` | Small helper for inspecting the raw feed. |
| `data/downloads.json` | Written by the page. The shared download list. |
| `data/listened.json` | Generated. Your Apple Podcasts history (heard and part-heard), published with the site. |
| `scripts/export_listened.py` | Reads the Mac's Podcasts database and writes `data/listened.json`. |
| `scripts/sync-listened.command` | Double-click version of the above, with a push. |
| `scripts/data_unchanged.py` | Lets the nightly job skip a commit when nothing really changed. |
| `.github/workflows/update-episodes.yml` | Rebuilds and commits the data nightly. |

Rebuild locally:

```bash
python3 scripts/build_data.py          # fetch the live feed and rewrite data/episodes.json
python3 -m http.server 8000            # then open http://localhost:8000
```

Opening `index.html` straight off disk will not work — browsers block `fetch()` over `file://`,
so the page needs to be served over HTTP (locally or via GitHub Pages).

## Keeping the listened list current

`data/listened.json` carries what you have already heard, so every browser and device
shows the same progress without importing anything. It is produced on the Mac from the
Podcasts app's own database:

```bash
python3 scripts/export_listened.py --push
```

or double-click `scripts/sync-listened.command`. To have it run by itself once a day,
install the launch agent described at the top of
`scripts/com.rest-is-history.listened.plist`.

The file holds two lists: episodes heard (with when, where Podcasts records it) and episodes
started but not finished (how far in, and the length). Positions under two minutes are left
out as accidental starts. `--stats` prints how the positions are spread, as numbers only.

**The file is published unencrypted, so anyone can read it** — this repository is public.
The page loads it on every browser and device with nothing to unlock.

To keep it private instead, run the export with `--encrypt`. The file is then AES-GCM under a
key stretched from a passphrase with PBKDF2-SHA256 (200,000 iterations); the passphrase is
never written to the repository, and the site asks for it once per browser, decrypts in the
page and remembers it locally. Set the passphrase once, in the macOS keychain:

```bash
security add-generic-password -a "$USER" -s rih-listened -w
```

The script also accepts `RIH_PASSPHRASE` in the environment, and prompts if it finds
neither. Encryption needs `cryptography` (`python3 -m pip install cryptography`). The nightly
launch agent runs without `--encrypt`, so add it to `scripts/sync-listened.command` as well.

Anything you mark or un-mark in the browser overrides the synced list for that episode,
and survives the next sync.

## Importing a one-off Apple export

Apple publishes no listening-history API, so this is a file import rather than a live sync —
re-run it whenever you want to top up. Two ways to get the file:

**From a Mac** (fastest). In Terminal:

```bash
cp ~/Library/Group\ Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite /tmp/mt.sqlite
sqlite3 -header -csv /tmp/mt.sqlite \
  "SELECT e.* FROM ZMTEPISODE e JOIN ZMTPODCAST p ON p.Z_PK=e.ZPODCAST WHERE p.ZTITLE LIKE '%Rest Is History%';" \
  > ~/Downloads/rih-playstate.csv
```

Terminal may need Full Disk Access to read that folder.

**From Apple's Data & Privacy export.** Request a copy of your data at privacy.apple.com including
Apple Media Services; the download contains `Podcasts Playstate.csv`. Takes a few days to arrive.

Either file goes into ⇅ Data → *Import from Apple Podcasts*. Episodes are matched on the audio
enclosure URL first, then episode GUID, then normalised title. An episode counts as listened when
Apple records play state 2, a play count above zero, or a playback position past 95% of its
duration; anything more than a minute in but unfinished is added to your queue instead. Rows for
*The Rest Is History Club* bonus episodes are skipped, since those are not in the public feed.

## About the classifications

`data/classifications.json` holds the editorial layer that makes historical sorting possible:
for each episode a start and end year, an era, one or two themes, a region, a canonical series
name, and a story arc. These are considered estimates of what an episode is *about* — a series on
Nelson is dated to his career, not to the day it was published.

The nightly job never invents classifications. When a new episode appears in the feed it:

1. inherits its series' existing classification if the title matches a series already classified
   (which covers most new episodes, since they arrive as parts of a running series); otherwise
2. is carried through under the era **Unsorted** and the arc **Unsorted**, so it is visible and
   searchable but obviously unplaced.

Anything sitting in *Unsorted* needs a human (or an LLM) to add an entry to
`data/classifications.json`, keyed by `n<episode number>` — for example `"n699"`:

```json
"n699": {
  "start": 1972, "end": 1998,
  "era": "Cold War & Post-War World",
  "theme": "War & Conflict", "theme2": "Politics & Power",
  "region": "Britain & Ireland",
  "series": "The Troubles",
  "strand": "Modern Britain & Ireland",
  "subject": "Northern Ireland from Bloody Sunday to the Good Friday Agreement",
  "confidence": "high",
  "apple": ""
}
```

The valid era, theme, region and arc strings are listed at the top of `scripts/build_data.py`.


## Journeys (listening order by place)

The **Journeys** tab lays a region — or a single nation inside it — out as one listening order,
so you can play through, say, Britain & Ireland from Stonehenge to Brexit without the episodes
jumping around.

* Order is worked out in `scripts/sequence.py` and stored on every episode: `rk` (run), `ro`
  (order in the run), `pt` (part number), `sq` (sequence year), `jk` (kind: `s` spine, `o`
  overview, `x` special) and `jx` (global rank). A *run* is consecutive parts of one story; it
  restarts when the part number goes back to 1, so Nelson's two runs or the two halves of the
  Hundred Years' War are separate. Runs stay together and sit at the median start year of their
  episodes. A *survey* run (several parts covering 250+ years, e.g. Ireland, Portugal, Baghdad)
  is spread out, each part at its own start year.
* Single episodes that span more than 150 years (a nation's whole history, a thematic romp such as
  Smuggling) are *overviews* and live on a shelf at the top of the journey; Christmas specials and
  format episodes are *specials* on a shelf at the end.
* Region membership comes from the nation tags in `data/nations.json` (`regions` maps each nation
  to a region), so a story appears in every region it touches.
* Hand corrections live in `data/sequence.json`: `spine` / `overview` (force an episode's kind),
  `sq` (fix an episode's sequence year), `survey_series` (spread a series' parts out).
* "Core history only" hides the music/film, food, sport and myth strands; "Hide episodes I've
  listened to" skips what you've heard. The panel at the top always shows the next unlistened
  episode with a one-tap Apple Podcasts button.
