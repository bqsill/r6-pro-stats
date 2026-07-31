"""Crawl SiegeGG competitions/matches into the local SQLite database."""

import datetime as dt
import re
import sqlite3

from . import config
from .api import Api, ApiError

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_period(text: str) -> tuple[dt.date, dt.date] | None:
    """Parse SiegeGG period strings like 'Jun 5 – Jul 19, 2026' or 'Aug 4 – 15, 2026'."""
    if not text:
        return None
    m = re.search(r",\s*(\d{4})\s*$", text)
    if not m:
        return None
    year = int(m.group(1))
    core = text[: m.start()]
    parts = [p.strip() for p in re.split(r"[–—-]", core) if p.strip()]
    if not parts:
        return None

    def parse_side(s: str, fallback_month: int | None):
        tokens = s.split()
        if len(tokens) == 2:
            return MONTHS.get(tokens[0][:3].lower()), int(tokens[1])
        if len(tokens) == 1 and tokens[0].isdigit() and fallback_month:
            return fallback_month, int(tokens[0])
        return None, None

    sm, sd = parse_side(parts[0], None)
    em, ed = parse_side(parts[-1], sm)
    if not sm or not em:
        return None
    start_year = year - 1 if sm > em else year  # cross-year periods carry only the end year
    try:
        return dt.date(start_year, sm, sd), dt.date(year, em, ed)
    except ValueError:
        return None


def parse_dash_pair(text: str | None) -> tuple[int | None, int | None]:
    """'38-27 (+11)' -> (38, 27)."""
    if not text:
        return None, None
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(text))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def comp_id_from_url(web_url: str) -> int | None:
    m = re.search(r"/competitions/(\d+)", web_url or "")
    return int(m.group(1)) if m else None


def sync(conn: sqlite3.Connection, days: int = 365, tiers: tuple[int, ...] = (1, 2),
         force: bool = False, comp_ids: list[int] | None = None, verbose: bool = True):
    api = Api(cache_dir=config.cache_dir())
    log = print if verbose else (lambda *a, **k: None)
    today = dt.date.today()
    window_start = today - dt.timedelta(days=days)
    rules = config.tier_rules()

    _sync_operators(conn, api)

    comps = _sync_competition_index(conn, api, rules, log)
    targets = []
    for c in comps:
        if comp_ids and c["id"] not in comp_ids:
            continue
        if not comp_ids:
            if c["tier"] not in tiers:
                continue
            period = (c["start_date"], c["end_date"])
            if not period[0] or not period[1]:
                continue
            if period[1] < window_start.isoformat() or period[0] > today.isoformat():
                continue
        targets.append(c)

    log(f"\n{len(targets)} competitions in window (last {days} days, tiers {tiers})")
    total_new = 0
    for c in targets:
        n = _sync_competition_matches(conn, api, c, force, log)
        total_new += n
    log(f"\ndone: {total_new} matches synced")


def _sync_operators(conn, api):
    data = api.get("/api/stats/operators", use_cache=False)
    rows = []
    for side_key in ("attackers", "defenders"):
        for op in (data.get(side_key) or {}).values():
            rows.append((op["id"], op["name"], op["side"], op.get("logo_url")))
    conn.executemany(
        "INSERT INTO operators(id, name, side, icon_url) VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, side=excluded.side, "
        "icon_url=excluded.icon_url", rows)
    conn.commit()


def _sync_competition_index(conn, api, rules, log):
    log("fetching competition index...")
    page, last_page = 1, 1
    listed = []
    while page <= last_page:
        data = api.get(f"/api/stats/competitions?page={page}")
        payload = data["competitions"]
        last_page = payload.get("last_page", 1)
        listed.extend(payload.get("data") or [])
        page += 1

    comps = []
    for item in listed:
        cid = comp_id_from_url(item.get("web_url"))
        if cid is None:
            continue
        detail = api.get(f"/api/stats/competitions/{cid}", use_cache=True)["competition"]
        period = parse_period(detail.get("date") or "")
        tier = config.classify_tier(detail["name"], rules)
        row = {
            "id": cid,
            "name": detail["name"],
            "short_name": detail.get("short_name"),
            "series": detail.get("series"),
            "region": detail.get("region"),
            "tier": tier,
            "start_date": period[0].isoformat() if period else None,
            "end_date": period[1].isoformat() if period else None,
            "online": 1 if detail.get("online") else 0,
            "prizepool": detail.get("prizepool"),
        }
        conn.execute(
            """INSERT INTO competitions(id, name, short_name, series, region, tier,
                                        start_date, end_date, online, prizepool)
               VALUES(:id, :name, :short_name, :series, :region, :tier,
                      :start_date, :end_date, :online, :prizepool)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, short_name=excluded.short_name,
                 series=excluded.series, region=excluded.region, tier=excluded.tier,
                 start_date=excluded.start_date, end_date=excluded.end_date,
                 online=excluded.online, prizepool=excluded.prizepool""", row)
        comps.append(row)
    conn.commit()
    log(f"indexed {len(comps)} competitions")
    return comps


def _sync_competition_matches(conn, api, comp, force, log) -> int:
    data = api.get(f"/api/stats/competitions/{comp['id']}/matches")
    results = [m for m in (data.get("results") or []) if m.get("has_results")]
    log(f"[{comp['tier'] or '?'}] {comp['name']}: {len(results)} finished matches", end=" ")

    synced_before = {r["id"] for r in conn.execute(
        "SELECT id FROM matches WHERE competition_id=? AND synced=1", (comp["id"],))}
    new = 0
    for m in results:
        rosters = m.get("rosters") or []
        for r in rosters:
            conn.execute(
                "INSERT INTO teams(id, name, tag, logo_url) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, tag=excluded.tag, "
                "logo_url=excluded.logo_url",
                (r["id"], r.get("name"), r.get("tag"), r.get("logo_url")))
        team_a = rosters[0]["id"] if len(rosters) > 0 else None
        team_b = rosters[1]["id"] if len(rosters) > 1 else None
        conn.execute(
            """INSERT INTO matches(id, competition_id, date, team_a, team_b, score_a,
                                   score_b, winner_team, playoff, bracket, round, has_results, synced)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,1,0)
               ON CONFLICT(id) DO UPDATE SET
                 date=excluded.date, score_a=excluded.score_a, score_b=excluded.score_b,
                 winner_team=excluded.winner_team, has_results=1""",
            (m["id"], comp["id"], m.get("date"), team_a, team_b, m.get("score_a"),
             m.get("score_b"), m.get("winner_id"), 1 if m.get("playoff") else 0,
             m.get("bracket"), m.get("round")))

        if m["id"] in synced_before and not force:
            continue
        try:
            _sync_match(conn, api, m["id"])
            new += 1
        except ApiError as e:
            log(f"\n  ! match {m['id']}: {e}", end=" ")
        conn.commit()
    conn.commit()
    log(f"({new} new)")
    return new


def _fetch_match_slim(api, match_id):
    path = f"/api/stats/matches/{match_id}"
    cached = api.get_cached(path)
    if cached is not None:
        return cached
    data = api.get(path)
    for g in data.get("games") or []:
        g.pop("rounds", None)  # kill-feed HTML, ~100KB/match, unused
    api.put_cache(path, data)
    return data


def _sync_match(conn, api, match_id):
    detail = _fetch_match_slim(api, match_id)
    ps = api.get(f"/api/stats/matches/{match_id}/player-stats", use_cache=True)

    player_team = {}
    for p in detail.get("players") or []:
        player_team[p["id"]] = p.get("roster_id")
        conn.execute(
            "INSERT INTO players(id, ign, real_name, image_url, flag_url) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET ign=excluded.ign, real_name=excluded.real_name, "
            "image_url=excluded.image_url, flag_url=excluded.flag_url",
            (p["id"], p.get("stylized_name") or p.get("ign"), p.get("name"),
             p.get("image_url"), p.get("flag")))

    for seq, g in enumerate(detail.get("games") or []):
        game_id = g["id"]
        mp = g.get("map") or {}
        if mp.get("id") is not None:
            conn.execute(
                "INSERT INTO maps(id, name, image_url) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                "image_url=excluded.image_url",
                (mp["id"], mp.get("name"), mp.get("image_url")))
        conn.execute(
            """INSERT INTO games(id, match_id, map_id, winner_team, win_score, loss_score, seq)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET winner_team=excluded.winner_team,
                 win_score=excluded.win_score, loss_score=excluded.loss_score""",
            (game_id, match_id, mp.get("id"), g.get("winner_id"),
             g.get("win_score"), g.get("loss_score"), seq))

        for team_id, wins in (g.get("round_wins_by_roster") or {}).items():
            conn.execute(
                "INSERT OR REPLACE INTO game_sides(game_id, team_id, atk_round_wins, def_round_wins) "
                "VALUES(?,?,?,?)",
                (game_id, int(team_id), (wins or {}).get("atk"), (wins or {}).get("def")))

        for ban in g.get("operator_bans") or []:
            op = ban.get("operator") or {}
            if op.get("id") is None:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO operator_bans(game_id, operator_id, team_id, ban_round) "
                "VALUES(?,?,?,?)",
                (game_id, op["id"], ban.get("stats_roster_id"), ban.get("ban_round")))

        game_stats = ps.get(str(game_id)) if isinstance(ps, dict) else None
        if not isinstance(game_stats, dict):
            continue
        for pid_str, s in game_stats.items():
            pid = to_int(s.get("player_id")) or to_int(pid_str)
            if pid is None:
                continue
            kills, deaths = parse_dash_pair(s.get("kd"))
            ok_k, ok_d = parse_dash_pair(s.get("ok"))
            ops = s.get("operators") or {}
            atk_op = (ops.get("atk") or {}).get("id")
            def_op = (ops.get("def") or {}).get("id")
            team_id = player_team.get(pid)
            won = 1 if team_id is not None and team_id == g.get("winner_id") else 0
            conn.execute(
                """INSERT OR REPLACE INTO game_player_stats(
                     game_id, player_id, team_id, won, kills, deaths, rating, kost, kpr,
                     hs, ok_kills, ok_deaths, srv, clutches, plants, disables, rounds,
                     atk_op, def_op)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (game_id, pid, team_id, won, kills, deaths, to_float(s.get("rating")),
                 to_float(s.get("kost")), to_float(s.get("kpr")), to_float(s.get("hs")),
                 ok_k, ok_d, to_float(s.get("srv")), to_int(s.get("clutches")),
                 to_int(s.get("plants")), to_int(s.get("disables")), to_int(s.get("rounds")),
                 atk_op, def_op))

    conn.execute("UPDATE matches SET synced=1 WHERE id=?", (match_id,))
