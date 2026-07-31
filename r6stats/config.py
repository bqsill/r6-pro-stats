"""Data directory layout and user-editable config (tier rules, patch windows)."""

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = Path(os.environ.get("R6STATS_DATA", PROJECT_ROOT / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "r6stats.sqlite"


def cache_dir() -> Path:
    return data_dir() / "cache"


# Tier classification: first matching rule wins (case-insensitive substring
# against the competition name). Tier 0 means "not classified" and is excluded
# from tier-filtered queries. Edit data/tiers.json to adjust.
DEFAULT_TIER_RULES = [
    {"contains": "major qualifier", "tier": 1},
    {"contains": "challenger", "tier": 2},
    {"contains": "qualifier", "tier": 2},
    {"contains": "last chance", "tier": 2},
    {"contains": "liga start", "tier": 2},
    {"contains": "element", "tier": 2},
    {"contains": "combine", "tier": 2},
    {"contains": "re:l0:ad", "tier": 2},
    {"contains": "dreamhack", "tier": 2},
    {"contains": "oga pit", "tier": 2},
    {"contains": "minor", "tier": 2},
    {"contains": "six invitational", "tier": 1},
    {"contains": "major", "tier": 1},
    {"contains": "esports world cup", "tier": 1},
    {"contains": "pro league", "tier": 1},
    {"contains": "league", "tier": 1},
]

# Patch/season windows (inclusive dates, UTC). Edit data/patches.json to
# adjust or extend when new seasons ship.
DEFAULT_PATCHES = [
    {"name": "Y10S1", "title": "Collision Point", "from": "2025-03-11", "to": "2025-06-09"},
    {"name": "Y10S2", "title": "Daybreak (Siege X)", "from": "2025-06-10", "to": "2025-09-01"},
    {"name": "Y10S3", "title": "High Stakes", "from": "2025-09-02", "to": "2025-12-01"},
    {"name": "Y10S4", "title": "Tenfold Pursuit", "from": "2025-12-02", "to": "2026-03-02"},
    {"name": "Y11S1", "title": "Silent Hunt", "from": "2026-03-03", "to": "2026-06-01"},
    {"name": "Y11S2", "title": "System Override", "from": "2026-06-02", "to": "2026-12-31"},
]


def _load_or_seed(filename: str, default):
    f = data_dir() / filename
    if not f.exists():
        f.write_text(json.dumps(default, indent=2))
        return default
    return json.loads(f.read_text())


def tier_rules() -> list[dict]:
    return _load_or_seed("tiers.json", DEFAULT_TIER_RULES)


def patches() -> list[dict]:
    return _load_or_seed("patches.json", DEFAULT_PATCHES)


def classify_tier(competition_name: str, rules: list[dict] | None = None) -> int:
    name = competition_name.lower()
    for rule in rules if rules is not None else tier_rules():
        if rule["contains"].lower() in name:
            return rule["tier"]
    return 0


def resolve_patch(name: str) -> dict | None:
    name = name.lower()
    for p in patches():
        if p["name"].lower() == name or p.get("title", "").lower() == name:
            return p
    return None
