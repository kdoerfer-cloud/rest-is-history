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
  shows hours logged, progress per era, and a "pick up where you left off" list of part-finished
  series. Everything is kept in your browser's local storage.
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
| `index.html` | The whole site — no build step, no dependencies, no external requests. |
| `data/episodes.json` | Generated. Every episode plus its classification. The page fetches this at load. |
| `data/classifications.json` | **Hand-curated.** The historical dating and grouping for each episode. |
| `scripts/build_data.py` | Merges the RSS feed with the classifications into `data/episodes.json`. |
| `scripts/fetch_feed.py` | Small helper for inspecting the raw feed. |
| `.github/workflows/update-episodes.yml` | Rebuilds and commits the data nightly. |

Rebuild locally:

```bash
python3 scripts/build_data.py          # fetch the live feed and rewrite data/episodes.json
python3 -m http.server 8000            # then open http://localhost:8000
```

Opening `index.html` straight off disk will not work — browsers block `fetch()` over `file://`,
so the page needs to be served over HTTP (locally or via GitHub Pages).

## Importing your Apple Podcasts history

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
