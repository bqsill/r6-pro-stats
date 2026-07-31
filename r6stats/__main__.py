"""r6stats — CLI for tier 1/2 Rainbow Six Siege pro-play statistics.

Data source: SiegeGG (siege.gg). Personal, rate-limited use.
"""

import argparse
import sys

from . import config, db, queries, sync, tables
from .queries import Filters, FilterError


def add_filter_args(p, with_tier=True):
    if with_tier:
        p.add_argument("--tier", type=int, choices=[1, 2],
                       help="tier of play (default: both)")
    p.add_argument("--region", help="na, eu, sa/latam, apac, intl (or raw text)")
    p.add_argument("--map", dest="map_name", help="map name filter, e.g. 'clubhouse'")
    p.add_argument("--patch", help="season window, e.g. Y10S3 (see 'patches')")
    p.add_argument("--from", dest="date_from", help="ISO date lower bound (default: 365 days ago)")
    p.add_argument("--to", dest="date_to", help="ISO date upper bound")


def make_filters(args, with_tier=True) -> Filters:
    return Filters(
        tier=getattr(args, "tier", None) if with_tier else None,
        region=args.region, map_name=args.map_name, patch=args.patch,
        date_from=args.date_from, date_to=args.date_to)


def scope_line(f: Filters, extra=""):
    bits = []
    bits.append(f"tier {f.tier}" if f.tier else "tiers 1+2")
    if f.region:
        bits.append(f"region={f.region}")
    if f.patch:
        bits.append(f"patch={f.patch}")
    elif f.date_from or f.date_to:
        bits.append(f"{f.date_from or '...'}..{f.date_to or 'now'}")
    else:
        bits.append("last 365 days")
    if f.map_name:
        bits.append(f"map~{f.map_name}")
    if extra:
        bits.append(extra)
    return "scope: " + ", ".join(bits)


PCT = ".0f"
PLAYER_COLS = [
    ("ign", "Player", "s"), ("team", "Team", "s"), ("maps", "Maps", "d"),
    ("rounds", "Rnds", "d"), ("rating", "Rating", ".2f"), ("kills", "K", "d"),
    ("deaths", "D", "d"), ("plus_minus", "+/-", "+d"), ("kd", "K/D", ".2f"),
    ("kpr", "KPR", ".2f"),
    ("kost", "KOST%", PCT), ("srv", "SRV%", PCT), ("hs", "HS%", PCT),
    ("ok_kills", "OK", "d"), ("ok_deaths", "OD", "d"), ("clutches", "1vX", "d"),
    ("map_win_pct", "MapW%", PCT),
]


def cmd_sync(args):
    conn = db.connect()
    sync.sync(conn, days=args.days, force=args.force,
              comp_ids=args.comp, tiers=(1, 2))


def cmd_players(args):
    conn = db.connect()
    f = make_filters(args)
    rows = queries.players(conn, f, sort=args.sort, min_rounds=args.min_rounds,
                           limit=args.limit)
    print(scope_line(f, f"min {args.min_rounds} rounds, sort={args.sort}"))
    print(tables.render(rows, PLAYER_COLS) if rows else "no data — run 'sync' first?")


def cmd_player(args):
    conn = db.connect()
    f = make_filters(args, with_tier=False)
    candidates = queries.find_player(conn, args.name)
    if not candidates:
        sys.exit(f"no player matching {args.name!r}")
    if len(candidates) > 1 and candidates[0]["ign"].lower() != args.name.lower():
        names = ", ".join(r["ign"] for r in candidates[:10])
        sys.exit(f"ambiguous name {args.name!r}: {names}")
    pid, ign = candidates[0]["id"], candidates[0]["ign"]

    summary = queries.player_summary(conn, pid, f)
    print(f"{ign} — {scope_line(f)}")
    if not summary or not summary["maps"]:
        sys.exit("no maps in this scope")
    print(tables.render([summary], [("ign", "Player", "s")] + PLAYER_COLS[2:]))

    per_map = queries.player_by_map(conn, pid, f)
    if per_map and not f.map_name:
        print("\nby map:")
        print(tables.render(per_map, [("map", "Map", "s")] + PLAYER_COLS[2:]))

    for side, label in (("atk", "attack operators (most-played per map)"),
                        ("def", "defend operators (most-played per map)")):
        ops = queries.player_operators(conn, pid, f, side)
        if ops:
            print(f"\n{label}:")
            print(tables.render(ops, [
                ("operator", "Operator", "s"), ("maps", "Maps", "d"),
                ("map_win_pct", "MapW%", PCT), ("rating", "Rating", ".2f")]))


def cmd_maps(args):
    conn = db.connect()
    f = make_filters(args)
    rows = queries.maps(conn, f)
    print(scope_line(f))
    print(tables.render(rows, [
        ("map", "Map", "s"), ("plays", "Plays", "d"), ("avg_rounds", "AvgRnds", ".1f"),
        ("atk_round_pct", "AtkRnd%", ".1f"), ("def_round_pct", "DefRnd%", ".1f"),
        ("one_round_pct", "1RndGames%", ".0f"),
    ]) if rows else "no data — run 'sync' first?")


def cmd_operators(args):
    conn = db.connect()
    f = make_filters(args)
    rows, games = queries.operators(conn, f, side=args.side, sort=args.sort)
    rows = rows[: args.limit]
    print(scope_line(f, f"{games} maps played"))
    print("pick% = share of team-maps where an operator was someone's most-played; "
          "per-round stats are full-map statlines of players who mained the op")
    print(tables.render(rows, [
        ("operator", "Operator", "s"), ("side", "Side", "s"),
        ("pick_pct", "Pick%", ".1f"), ("ban_pct", "Ban%", ".1f"),
        ("picks", "Maps", "d"), ("rounds", "Rnds", "d"),
        ("kpr", "KPR", ".2f"), ("kd", "K/D", ".2f"), ("kost", "KOST%", PCT),
        ("srv", "SRV%", PCT), ("hs", "HS%", PCT), ("clutches", "1vX", "d"),
        ("map_win_pct", "MapW%", PCT), ("rating", "Rating", ".2f"),
    ]) if rows else "no data — run 'sync' first?")


def cmd_competitions(args):
    conn = db.connect()
    f = make_filters(args)
    rows = queries.competitions(conn, f, include_unsynced=args.all)
    print(tables.render(rows, [
        ("id", "ID", "d"), ("name", "Competition", "s"), ("tier", "Tier", "d"),
        ("region", "Region", "s"), ("start_date", "Start", "s"),
        ("end_date", "End", "s"), ("matches", "Matches", "d"),
    ]) if rows else "nothing synced yet — run 'sync'")
    print("\ntier rules: data/tiers.json (tier 0 = unclassified, excluded)")


def cmd_patches(_args):
    print(tables.render(config.patches(), [
        ("name", "Patch", "s"), ("title", "Title", "s"),
        ("from", "From", "s"), ("to", "To", "s")]))
    print("\nedit data/patches.json to adjust windows")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="r6stats",
        description="Tier 1/2 Rainbow Six Siege pro-play stats (data: siege.gg)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sync", help="download/refresh match data")
    p.add_argument("--days", type=int, default=365, help="window size (default 365)")
    p.add_argument("--force", action="store_true", help="refetch already-synced matches")
    p.add_argument("--comp", type=int, action="append",
                   help="sync only this competition id (repeatable)")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("players", help="player leaderboard")
    add_filter_args(p)
    p.add_argument("--sort", default="rating",
                   help=f"one of: {', '.join(queries.PLAYER_SORTS)}")
    p.add_argument("--min-rounds", type=int, default=75)
    p.add_argument("--limit", type=int, default=0, help="0 = all players (default)")
    p.set_defaults(fn=cmd_players)

    p = sub.add_parser("player", help="single player deep-dive")
    p.add_argument("name")
    add_filter_args(p, with_tier=False)
    p.set_defaults(fn=cmd_player)

    p = sub.add_parser("maps", help="map stats")
    add_filter_args(p)
    p.set_defaults(fn=cmd_maps)

    p = sub.add_parser("operators", help="operator pick/ban stats")
    add_filter_args(p)
    p.add_argument("--side", choices=["atk", "def"])
    p.add_argument("--sort", default="pick",
                   help="pick, ban, winrate, rating, kd, kpr, kost, rounds")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(fn=cmd_operators)

    p = sub.add_parser("competitions", help="synced competitions + tier classification")
    add_filter_args(p)
    p.add_argument("--all", action="store_true", help="include unsynced competitions")
    p.set_defaults(fn=cmd_competitions)

    p = sub.add_parser("patches", help="configured patch/season windows")
    p.set_defaults(fn=cmd_patches)

    p = sub.add_parser("assets", help="download map blueprints for the planning tab")
    p.add_argument("--force", action="store_true", help="re-download even if present")
    p.add_argument("--no-upscale", action="store_true", help="keep the original 1600x900")
    p.set_defaults(fn=lambda a: __import__("r6stats.assets", fromlist=["fetch"]).fetch(
        force=a.force, upscale=not a.no_upscale))

    p = sub.add_parser("gui", help="open the desktop app")
    p.set_defaults(fn=lambda _args: __import__(
        "r6stats.gui", fromlist=["run"]).run())

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except FilterError as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        sys.exit("\ninterrupted")


if __name__ == "__main__":
    main()
