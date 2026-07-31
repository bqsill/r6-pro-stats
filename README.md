# r6-pro-stats

Tier 1 and tier 2 Rainbow Six Siege pro-play statistics, on your machine — a
CLI and a desktop app for player, operator, and map stats that you can slice by
**tier of play, region, patch or date range, and map**, plus a strat-planning
whiteboard built on the official map blueprints.

Pro-play stats for R6 are scattered and mostly unfilterable. This pulls
match-level data once, stores it in SQLite, and does its own aggregation — so
you can ask things no public site will answer, like *"Kafe defender pick rates
in tier 2 EU on the current patch"* or *"this player's per-map K/D on Bank."*

Covers the **last 365 days** by default. Everything runs offline after the
initial sync.

---

## Requirements

| | |
|---|---|
| CLI | Python 3.11+, **standard library only** |
| Desktop app | the above plus [`pywebview`](https://pywebview.flowrl.com/) |
| 2× blueprint upscaling (optional) | `pillow` |
| Regenerating room callouts (rarely) | `numpy`, `scipy`, `pillow` |

## Installation

**1. Get the code**

```sh
git clone https://github.com/bqsill/r6-pro-stats.git
cd r6-pro-stats
python3 --version          # need 3.11 or newer
```

**2. Download the match data** — the only step the CLI actually needs:

```sh
python3 -m r6stats sync
```

First run takes roughly 15–25 minutes: it crawls every tier 1/2 competition
overlapping the last 365 days and stores per-map player statlines, map results,
and operator bans. It is **incremental** — re-run it after event days and it
fetches only new matches. Responses are cached in `data/cache/`, so re-syncs
cost almost nothing.

At this point the CLI is fully usable:

```sh
python3 -m r6stats players --tier 1 --limit 15
```

**3. Set up the desktop app** (optional)

```sh
python3 -m venv .venv
.venv/bin/pip install pywebview pillow
.venv/bin/python -m r6stats assets     # map blueprints, ~50 MB, one-time
.venv/bin/python -m r6stats gui
```

`assets` downloads the official floor blueprints from Ubisoft's CDN — they are
not shipped in this repo. Skip it and the app still works; only the Planning
tab needs them, and it will tell you to run it. Pillow is optional but doubles
the blueprint resolution, which matters when zooming.

On Windows and Linux use `.venv\Scripts\python` / `.venv/bin/python`
respectively; `pywebview` needs a system webview
([GTK/Qt on Linux](https://pywebview.flowrl.com/guide/installation.html),
Edge WebView2 on Windows, nothing extra on macOS).

**Storage** — a full sync is about 4 MB of database plus 42 MB of response
cache; blueprints add ~50 MB. Everything lives under `data/` (gitignored)
except the blueprints, which sit in `r6stats/web/maps/`.

A current sync holds roughly **1,250 matches / 2,100 maps / 20,000 player
statlines** across 36 competitions and 700 players.

---

## CLI

```sh
python3 -m r6stats <command> [filters] [options]
```

| Command | What it does |
|---|---|
| `sync` | download/refresh match data (`--days`, `--force`, `--comp ID`) |
| `assets` | download map blueprints for the planning tab (`--force`, `--no-upscale`) |
| `players` | leaderboard (`--sort`, `--min-rounds`, `--limit`) |
| `player NAME` | one player: totals, per-map splits, operator usage |
| `maps` | plays, attack/defence round win %, average rounds |
| `operators` | pick/ban rates with full per-round stats (`--side`, `--sort`) |
| `competitions` | what's synced and how each event was tiered (`--all`) |
| `patches` | configured season windows |
| `gui` | open the desktop app |

### Filters

Shared by every query command:

| Flag | Values |
|---|---|
| `--tier` | `1`, `2` (default: both; not available on `player`) |
| `--region` | `na`, `eu`/`emea`, `sa`/`latam`, `apac`, `intl`, or raw text |
| `--patch` | `Y10S1` … `Y11S2` (see `patches`) |
| `--from` / `--to` | ISO dates (default: last 365 days) |
| `--map` | substring, e.g. `clubhouse` |

Sort keys — players: `rating`, `kills`, `kd`, `kpr`, `kost`, `srv`, `hs`,
`rounds`, `maps`, `winrate`, `ok`, `clutches`, `plusminus`. Operators: `pick`,
`ban`, `winrate`, `rating`, `kd`, `kpr`, `kost`, `rounds`.

### Examples

```sh
python3 -m r6stats players --tier 1 --region eu --patch Y11S1
python3 -m r6stats players --sort kd --min-rounds 300
python3 -m r6stats player Shaiiko --map bank
python3 -m r6stats operators --tier 2 --side def --sort ban
python3 -m r6stats operators --patch Y11S2 --map chalet --sort kost
python3 -m r6stats maps --region na --from 2026-03-01
```

Stats available per player and per operator: rating, K, D, +/-, K/D, KPR,
KOST%, survival%, HS%, opening kills/deaths, 1vX clutches, rounds, maps, and
map win %.

---

## Desktop app

A native window over the same database. Four tabs — **Players**, **Operators**,
**Maps**, **Planning** — sharing the filter bar above. Every column sorts on
click, player rows open a deep-dive, and rows carry real player photos, team
logos, and operator icons.

### Planning tab

A strat whiteboard on the official Ubisoft floor blueprints.

| Action | How |
|---|---|
| Pick map / floor | map dropdown, then the named floor buttons (Basement → Roof) |
| Draw | pencil tool + colour wheel or the 8 swatches |
| Erase / clear floor | eraser tool / 🗑 |
| Undo / redo stroke | `⌘Z` / `⌘X` (per floor, 30 steps, clearing is undoable) |
| Zoom / pan | scroll or `+ − ⤢`; drag to pan (with no draw tool active) |
| Add operators | `+` beside Attackers/Defenders — up to 5 a side |
| Place operator | click its roster chip, then click the map |
| Place gadget marker | `◆` on the chip, then the map (up to 3 per operator) |
| Move / remove token | drag / double-click |
| Room callout | hover the map — the name shows bottom-left |

Tokens and drawings belong to the floor they were made on: they hide when you
switch floors and return exactly where you left them. Everything autosaves per
map into `data/plans/`.

---

## How it works

```
SiegeGG JSON API  ──sync──▶  SQLite (matches, games, player statlines, bans)
                                  │
                                  ├─▶  CLI aggregation queries
                                  └─▶  desktop app (pywebview + JS front end)
```

`sync` walks competitions → matches → per-match games and player stats,
rate-limited to ~3 requests/second and cached on disk. The database keeps
**per-map, per-player** statlines rather than pre-aggregated totals, which is
what makes arbitrary tier/region/patch/map filtering possible. Rating, KOST,
and survival are round-weighted when aggregated; K/D and KPR are computed from
summed kills, deaths, and rounds.

## Configuration

Both files are seeded on first run and meant to be edited:

- **`data/tiers.json`** — ordered substring rules mapping competition names to
  tier 1 / tier 2 (first match wins; tier 0 is excluded). Check the result with
  `competitions --all`.
- **`data/patches.json`** — season windows used by `--patch`. Add an entry when
  a new season ships and it appears in the CLI and the app's period dropdown.

Set `R6STATS_DATA` to relocate the data directory (database, cache, plans,
config).

## Project layout

```
r6stats/
  __main__.py      CLI entry point and table formatting
  api.py           SiegeGG client: rate limiting, retries, disk cache
  sync.py          crawler → SQLite
  db.py            schema and migrations
  queries.py       filters and aggregation SQL
  gui.py           pywebview window + JS-facing API
  web/
    index.html     the whole front end (no build step, no frameworks)
    icons/         76 operator SVGs
    maps/          floor blueprints, maps.json, rooms.json
data/              database, response cache, saved plans, config  (gitignored)
```

## Data sources and attribution

| Source | Used for | Licence | Shipped here? |
|---|---|---|---|
| [SiegeGG](https://siege.gg) | all match, player, map, operator statistics | undocumented public JSON API | no — fetched by `sync` |
| [Ubisoft](https://www.ubisoft.com/en-us/game/rainbow-six/siege) | official floor blueprints | Ubisoft assets | no — fetched by `assets` |
| [r6operators](https://github.com/marcopixel/r6operators) | operator icons | MIT | yes, with notice |
| [r6maps](https://github.com/capajon/r6maps) | room callout names/positions | MIT | derived, with notice |

Full licence texts are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
This project's own code is MIT ([LICENSE](LICENSE)).

Blueprints are upscaled 2× locally (Lanczos + light sharpen) because 1600×900
is the highest resolution Ubisoft publishes. Room callouts were transferred
onto those blueprints by cross-correlating the wall masks of both renders to
solve the scale and offset, then verified per map by overlay.

**This is an unofficial fan project.** Rainbow Six Siege and all related
imagery are the property of Ubisoft Entertainment; this tool is not affiliated
with or endorsed by Ubisoft or SiegeGG. Statistics are fetched for personal
analysis, rate-limited to ~3 requests/second and cached to minimise load. If
you run one of these services and want something changed, please open an issue.

## Limitations

- **Operator stats are per-map, not per-round.** SiegeGG records each player's
  *most-played* operator per map and side, so an operator's pick share and
  per-round stats attribute that player's whole map statline to it. Bans are
  exact.
- **No assists** in the source data, so K/D is shown rather than KDA.
- **Tier 2 coverage** extends only as far as SiegeGG tracks (Challenger
  Leagues, Liga START, ELEMENT, Combine, RE:L0:AD, SI qualifiers) — smaller
  national leagues aren't in the data.
- **Lair and Nighthaven Labs have no room callouts** — they postdate the r6maps
  dataset and no comparable open source exists.
- Tiering is rule-based on competition names; edit `data/tiers.json` if you
  disagree with a call.
- Blueprint and icon assets are vendored for offline use and remain the
  property of their respective owners; the statistics are for personal
  analysis, not redistribution.
