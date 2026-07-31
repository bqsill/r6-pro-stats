"""SQLite schema and connection helpers."""

import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS competitions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    series TEXT,
    region TEXT,
    tier INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    online INTEGER,
    prizepool TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    name TEXT,
    tag TEXT,
    logo_url TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    ign TEXT,
    real_name TEXT,
    image_url TEXT,
    flag_url TEXT
);

CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY,
    name TEXT,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS operators (
    id INTEGER PRIMARY KEY,
    name TEXT,
    side TEXT,  -- ATTACK / DEFEND
    icon_url TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    competition_id INTEGER NOT NULL REFERENCES competitions(id),
    date TEXT,                -- ISO8601 UTC
    team_a INTEGER REFERENCES teams(id),
    team_b INTEGER REFERENCES teams(id),
    score_a INTEGER,
    score_b INTEGER,
    winner_team INTEGER,
    playoff INTEGER,
    bracket TEXT,
    round TEXT,
    has_results INTEGER,
    synced INTEGER NOT NULL DEFAULT 0   -- 1 once games/player stats stored
);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_comp ON matches(competition_id);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    map_id INTEGER REFERENCES maps(id),
    winner_team INTEGER,
    win_score INTEGER,
    loss_score INTEGER,
    seq INTEGER
);
CREATE INDEX IF NOT EXISTS idx_games_match ON games(match_id);

-- Per-game, per-team attack/defense round wins (two rows per game).
CREATE TABLE IF NOT EXISTS game_sides (
    game_id INTEGER NOT NULL REFERENCES games(id),
    team_id INTEGER NOT NULL,
    atk_round_wins INTEGER,
    def_round_wins INTEGER,
    PRIMARY KEY (game_id, team_id)
);

CREATE TABLE IF NOT EXISTS operator_bans (
    game_id INTEGER NOT NULL REFERENCES games(id),
    operator_id INTEGER NOT NULL REFERENCES operators(id),
    team_id INTEGER,
    ban_round INTEGER,
    PRIMARY KEY (game_id, operator_id, team_id)
);

-- Per-game (i.e. per-map) player statlines. atk_op/def_op are the player's
-- most-played operator on each side for that map, per SiegeGG.
CREATE TABLE IF NOT EXISTS game_player_stats (
    game_id INTEGER NOT NULL REFERENCES games(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER,
    won INTEGER,
    kills INTEGER,
    deaths INTEGER,
    rating REAL,
    kost REAL,
    kpr REAL,
    hs REAL,
    ok_kills INTEGER,
    ok_deaths INTEGER,
    srv REAL,
    clutches INTEGER,
    plants INTEGER,
    disables INTEGER,
    rounds INTEGER,
    atk_op INTEGER REFERENCES operators(id),
    def_op INTEGER REFERENCES operators(id),
    PRIMARY KEY (game_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_gps_player ON game_player_stats(player_id);
"""


# Columns added after the initial schema; applied to pre-existing databases.
MIGRATIONS = [
    ("teams", "logo_url", "TEXT"),
    ("players", "image_url", "TEXT"),
    ("players", "flag_url", "TEXT"),
    ("maps", "image_url", "TEXT"),
    ("operators", "icon_url", "TEXT"),
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for table, column, ctype in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ctype}")
    conn.commit()
    return conn
