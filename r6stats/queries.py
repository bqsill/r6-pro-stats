"""Aggregation queries with shared tier/region/time/map filters."""

import datetime as dt
import sqlite3

from . import config

REGION_ALIASES = {
    "na": ["north america"],
    "eu": ["europe"],
    "emea": ["europe"],
    "sa": ["latin america", "south america", "brazil"],
    "latam": ["latin america", "south america", "brazil"],
    "br": ["latin america", "south america", "brazil"],
    "apac": ["asia", "pacific", "oceania", "japan", "korea", "china"],
    "asia": ["asia", "pacific", "oceania", "japan", "korea", "china"],
    "intl": ["international"],
    "global": ["international"],
}


class FilterError(Exception):
    pass


class Filters:
    """Shared filters. Joins assume aliases: s=game_player_stats, g=games,
    m=matches, c=competitions, mp=maps."""

    def __init__(self, tier=None, region=None, map_name=None, patch=None,
                 date_from=None, date_to=None, days_default=365):
        self.tier = tier
        self.region = region
        self.map_name = map_name
        self.patch = patch
        self.date_from = date_from
        self.date_to = date_to
        self.days_default = days_default

    def where(self, with_map=True) -> tuple[str, list]:
        conds, params = ["m.has_results = 1"], []
        if self.tier is not None:
            conds.append("c.tier = ?")
            params.append(self.tier)
        else:
            conds.append("c.tier IN (1, 2)")
        if self.region:
            needles = REGION_ALIASES.get(self.region.lower(), [self.region.lower()])
            conds.append("(" + " OR ".join(["LOWER(c.region) LIKE ?"] * len(needles)) + ")")
            params.extend(f"%{n}%" for n in needles)

        date_from, date_to = self.date_from, self.date_to
        if self.patch:
            p = config.resolve_patch(self.patch)
            if not p:
                known = ", ".join(x["name"] for x in config.patches())
                raise FilterError(f"unknown patch {self.patch!r} (known: {known})")
            date_from, date_to = p["from"], p["to"]
        if not date_from:
            date_from = (dt.date.today() - dt.timedelta(days=self.days_default)).isoformat()
        conds.append("date(m.date) >= ?")
        params.append(date_from)
        if date_to:
            conds.append("date(m.date) <= ?")
            params.append(date_to)

        if with_map and self.map_name:
            conds.append("LOWER(mp.name) LIKE ?")
            params.append(f"%{self.map_name.lower()}%")
        return " AND ".join(conds), params


PLAYER_BASE = """
FROM game_player_stats s
JOIN games g ON g.id = s.game_id
JOIN matches m ON m.id = g.match_id
JOIN competitions c ON c.id = m.competition_id
LEFT JOIN maps mp ON mp.id = g.map_id
JOIN players p ON p.id = s.player_id
"""

PLAYER_AGG = """
COUNT(DISTINCT m.id)                                    AS matches,
COUNT(*)                                                AS maps,
SUM(s.rounds)                                           AS rounds,
SUM(s.kills)                                            AS kills,
SUM(s.deaths)                                           AS deaths,
SUM(s.kills) - SUM(s.deaths)                            AS plus_minus,
1.0 * SUM(s.kills) / NULLIF(SUM(s.deaths), 0)           AS kd,
1.0 * SUM(s.rating * s.rounds) / NULLIF(SUM(s.rounds), 0) AS rating,
1.0 * SUM(s.kills) / NULLIF(SUM(s.rounds), 0)           AS kpr,
1.0 * SUM(s.kost * s.rounds) / NULLIF(SUM(s.rounds), 0) AS kost,
1.0 * SUM(s.srv * s.rounds) / NULLIF(SUM(s.rounds), 0)  AS srv,
1.0 * SUM(s.hs * s.kills) / NULLIF(SUM(s.kills), 0)     AS hs,
SUM(s.ok_kills)                                         AS ok_kills,
SUM(s.ok_deaths)                                        AS ok_deaths,
SUM(s.clutches)                                         AS clutches,
100.0 * AVG(s.won)                                      AS map_win_pct
"""

PLAYER_SORTS = {
    "rating": "rating", "kills": "kills", "kd": "1.0*SUM(s.kills)/NULLIF(SUM(s.deaths),0)",
    "kpr": "kpr", "kost": "kost", "srv": "srv", "hs": "hs", "rounds": "rounds",
    "maps": "maps", "winrate": "map_win_pct", "ok": "ok_kills", "clutches": "clutches",
    "plusminus": "plus_minus",
}


def players(conn: sqlite3.Connection, f: Filters, sort="rating", min_rounds=75, limit=None):
    order = PLAYER_SORTS.get(sort)
    if not order:
        raise FilterError(f"unknown sort {sort!r} (known: {', '.join(PLAYER_SORTS)})")
    limit = -1 if not limit else limit  # SQLite: LIMIT -1 = unlimited
    where, params = f.where()
    sql = f"""
    SELECT p.id AS player_id, p.ign,
      (SELECT t.tag FROM game_player_stats s2
         JOIN games g2 ON g2.id = s2.game_id
         JOIN matches m2 ON m2.id = g2.match_id
         JOIN teams t ON t.id = s2.team_id
        WHERE s2.player_id = p.id ORDER BY m2.date DESC LIMIT 1) AS team,
      {PLAYER_AGG}
    {PLAYER_BASE}
    WHERE {where}
    GROUP BY p.id
    HAVING SUM(s.rounds) >= ?
    ORDER BY {order} DESC
    LIMIT ?"""
    return conn.execute(sql, [*params, min_rounds, limit]).fetchall()


def find_player(conn, name):
    rows = conn.execute(
        "SELECT id, ign FROM players WHERE LOWER(ign) LIKE ? ORDER BY LENGTH(ign)",
        (f"%{name.lower()}%",)).fetchall()
    exact = [r for r in rows if r["ign"].lower() == name.lower()]
    return exact or rows


def player_summary(conn, player_id, f: Filters):
    where, params = f.where()
    sql = f"""SELECT p.ign, {PLAYER_AGG} {PLAYER_BASE}
              WHERE {where} AND p.id = ? GROUP BY p.id"""
    return conn.execute(sql, [*params, player_id]).fetchone()


def player_by_map(conn, player_id, f: Filters):
    where, params = f.where()
    sql = f"""SELECT mp.name AS map, {PLAYER_AGG} {PLAYER_BASE}
              WHERE {where} AND p.id = ? GROUP BY mp.id ORDER BY maps DESC"""
    return conn.execute(sql, [*params, player_id]).fetchall()


def player_operators(conn, player_id, f: Filters, side):
    op_col = "s.atk_op" if side == "atk" else "s.def_op"
    where, params = f.where()
    sql = f"""
    SELECT o.name AS operator, COUNT(*) AS maps,
           1.0 * SUM(s.kills) / NULLIF(SUM(s.rounds), 0) AS kpr,
           1.0 * SUM(s.kills) / NULLIF(SUM(s.deaths), 0) AS kd,
           1.0 * SUM(s.kost * s.rounds) / NULLIF(SUM(s.rounds), 0) AS kost,
           100.0 * AVG(s.won) AS map_win_pct,
           1.0 * SUM(s.rating * s.rounds) / NULLIF(SUM(s.rounds), 0) AS rating
    {PLAYER_BASE}
    JOIN operators o ON o.id = {op_col}
    WHERE {where} AND p.id = ?
    GROUP BY o.id ORDER BY maps DESC LIMIT 8"""
    return conn.execute(sql, [*params, player_id]).fetchall()


def maps(conn: sqlite3.Connection, f: Filters):
    where, params = f.where()
    sql = f"""
    SELECT mp.name AS map,
      COUNT(*) AS plays,
      1.0 * AVG(g.win_score + g.loss_score) AS avg_rounds,
      100.0 * SUM(sd.atk_w) / NULLIF(SUM(sd.atk_w + sd.def_w), 0) AS atk_round_pct,
      100.0 * SUM(sd.def_w) / NULLIF(SUM(sd.atk_w + sd.def_w), 0) AS def_round_pct,
      100.0 * AVG(CASE WHEN g.win_score - g.loss_score = 1 THEN 1.0 ELSE 0 END) AS one_round_pct
    FROM games g
    JOIN matches m ON m.id = g.match_id
    JOIN competitions c ON c.id = m.competition_id
    JOIN maps mp ON mp.id = g.map_id
    JOIN (SELECT game_id, SUM(atk_round_wins) AS atk_w, SUM(def_round_wins) AS def_w
            FROM game_sides GROUP BY game_id) sd ON sd.game_id = g.id
    WHERE {where}
    GROUP BY mp.id ORDER BY plays DESC"""
    return conn.execute(sql, params).fetchall()


def _total_games(conn, f: Filters):
    where, params = f.where()
    sql = f"""
    SELECT COUNT(DISTINCT g.id) AS n
    FROM games g
    JOIN matches m ON m.id = g.match_id
    JOIN competitions c ON c.id = m.competition_id
    LEFT JOIN maps mp ON mp.id = g.map_id
    WHERE {where}"""
    row = conn.execute(sql, params).fetchone()
    return row["n"] or 0


def operators(conn: sqlite3.Connection, f: Filters, side=None, sort="pick"):
    """Pick presence is based on each player's most-played operator per map
    (10 slots per side per map). Bans are exact."""
    games_total = _total_games(conn, f)
    result = {}
    for s, col in (("ATTACK", "s.atk_op"), ("DEFEND", "s.def_op")):
        if side and side != {"ATTACK": "atk", "DEFEND": "def"}[s]:
            continue
        where, params = f.where()
        sql = f"""
        SELECT o.id, o.name AS operator, o.side,
          COUNT(*) AS picks,
          SUM(s.rounds) AS rounds,
          SUM(s.kills) AS kills,
          SUM(s.deaths) AS deaths,
          1.0 * SUM(s.kills) / NULLIF(SUM(s.rounds), 0) AS kpr,
          1.0 * SUM(s.kills) / NULLIF(SUM(s.deaths), 0) AS kd,
          1.0 * SUM(s.kost * s.rounds) / NULLIF(SUM(s.rounds), 0) AS kost,
          1.0 * SUM(s.srv * s.rounds) / NULLIF(SUM(s.rounds), 0) AS srv,
          1.0 * SUM(s.hs * s.kills) / NULLIF(SUM(s.kills), 0) AS hs,
          SUM(s.ok_kills) AS ok_kills,
          SUM(s.ok_deaths) AS ok_deaths,
          SUM(s.clutches) AS clutches,
          100.0 * AVG(s.won) AS map_win_pct,
          1.0 * SUM(s.rating * s.rounds) / NULLIF(SUM(s.rounds), 0) AS rating
        {PLAYER_BASE}
        JOIN operators o ON o.id = {col}
        WHERE {where}
        GROUP BY o.id"""
        for r in conn.execute(sql, params):
            result[r["id"]] = dict(r)

    where, params = f.where()
    ban_sql = f"""
    SELECT b.operator_id AS id, o.name AS operator, o.side,
           COUNT(DISTINCT b.game_id) AS ban_games
    FROM operator_bans b
    JOIN operators o ON o.id = b.operator_id
    JOIN games g ON g.id = b.game_id
    JOIN matches m ON m.id = g.match_id
    JOIN competitions c ON c.id = m.competition_id
    LEFT JOIN maps mp ON mp.id = g.map_id
    WHERE {where}
    GROUP BY b.operator_id"""
    for r in conn.execute(ban_sql, params):
        if side and side != {"ATTACK": "atk", "DEFEND": "def"}[r["side"]]:
            continue
        result.setdefault(r["id"], {"operator": r["operator"], "side": r["side"],
                                    "picks": 0, "rounds": None, "kills": None,
                                    "deaths": None, "kpr": None, "kd": None,
                                    "kost": None, "srv": None, "hs": None,
                                    "ok_kills": None, "ok_deaths": None,
                                    "clutches": None, "map_win_pct": None,
                                    "rating": None})
        result[r["id"]]["ban_games"] = r["ban_games"]

    team_maps = 2 * games_total  # two teams pick per map
    rows = []
    for r in result.values():
        r.setdefault("ban_games", 0)
        r["pick_pct"] = 100.0 * r["picks"] / team_maps if team_maps else None
        r["ban_pct"] = 100.0 * r["ban_games"] / games_total if games_total else None
        rows.append(r)
    key = {"pick": "pick_pct", "ban": "ban_pct", "winrate": "map_win_pct",
           "rating": "rating", "kd": "kd", "kpr": "kpr", "kost": "kost",
           "rounds": "rounds"}.get(sort)
    if not key:
        raise FilterError(
            f"unknown sort {sort!r} (known: pick, ban, winrate, rating, kd, kpr, kost, rounds)")
    rows.sort(key=lambda r: (r.get(key) is not None, r.get(key)), reverse=True)
    return rows, games_total


def competitions(conn: sqlite3.Connection, f: Filters, include_unsynced=False):
    conds, params = [], []
    if f.tier is not None:
        conds.append("c.tier = ?")
        params.append(f.tier)
    if f.region:
        needles = REGION_ALIASES.get(f.region.lower(), [f.region.lower()])
        conds.append("(" + " OR ".join(["LOWER(c.region) LIKE ?"] * len(needles)) + ")")
        params.extend(f"%{n}%" for n in needles)
    date_from = f.date_from or (dt.date.today() - dt.timedelta(days=f.days_default)).isoformat()
    conds.append("c.end_date >= ?")
    params.append(date_from)
    having = "" if include_unsynced else "HAVING COUNT(m.id) > 0"
    sql = f"""
    SELECT c.id, c.name, c.tier, c.region, c.start_date, c.end_date,
           COUNT(m.id) AS matches
    FROM competitions c
    LEFT JOIN matches m ON m.competition_id = c.id AND m.synced = 1
    WHERE {' AND '.join(conds)}
    GROUP BY c.id {having}
    ORDER BY c.end_date DESC"""
    return conn.execute(sql, params).fetchall()
