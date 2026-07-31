"""Desktop GUI: native pywebview window over the local stats database.

Run with:  .venv/bin/python -m r6stats gui
"""

import json
import re
import unicodedata
from pathlib import Path

from . import config, db, queries
from .queries import Filters, FilterError

WEB_DIR = Path(__file__).resolve().parent / "web"


def op_icon(name: str, remote_url: str | None) -> dict:
    """Prefer the vendored r6operators glyph (colored for dark backgrounds);
    fall back to the remote SiegeGG icon rendered on a light chip."""
    slug = unicodedata.normalize("NFKD", (name or "").lower())
    slug = re.sub(r"[^a-z0-9]", "", slug.encode("ascii", "ignore").decode())
    if (WEB_DIR / "icons" / f"{slug}.svg").exists():
        return {"icon_url": f"icons/{slug}.svg", "icon_chip": False}
    return {"icon_url": remote_url, "icon_chip": True}


def _filters(f: dict) -> Filters:
    f = f or {}
    return Filters(
        tier=f.get("tier"), region=f.get("region"), map_name=f.get("map"),
        patch=f.get("patch"), date_from=f.get("from"), date_to=f.get("to"))


class JsApi:
    """Methods callable from JS via window.pywebview.api.*  (fresh sqlite
    connection per call: pywebview invokes these off the main thread)."""

    def _wrap(self, fn):
        try:
            return {"ok": True, "data": fn()}
        except FilterError as e:
            return {"ok": False, "error": str(e)}

    def options(self):
        def go():
            conn = db.connect()
            maps = [r["name"] for r in conn.execute(
                "SELECT DISTINCT name FROM maps WHERE name IS NOT NULL ORDER BY name")]
            n = conn.execute(
                "SELECT COUNT(*) AS n, MIN(date(date)) AS lo, MAX(date(date)) AS hi "
                "FROM matches WHERE synced=1").fetchone()
            return {"maps": maps, "patches": config.patches(),
                    "matches": n["n"], "date_lo": n["lo"], "date_hi": n["hi"]}
        return self._wrap(go)

    def _latest_teams(self, conn, player_ids):
        if not player_ids:
            return {}
        qmarks = ",".join("?" * len(player_ids))
        sql = f"""
        SELECT player_id, team_id FROM (
          SELECT s.player_id, s.team_id,
                 ROW_NUMBER() OVER (PARTITION BY s.player_id ORDER BY m.date DESC) rn
          FROM game_player_stats s
          JOIN games g ON g.id = s.game_id
          JOIN matches m ON m.id = g.match_id
          WHERE s.player_id IN ({qmarks})
        ) WHERE rn = 1"""
        pt = {r["player_id"]: r["team_id"] for r in conn.execute(sql, list(player_ids))}
        teams = {}
        for r in conn.execute("SELECT id, tag, name, logo_url FROM teams"):
            teams[r["id"]] = dict(r)
        return {pid: teams.get(tid) for pid, tid in pt.items()}

    def players(self, f=None, sort="rating", min_rounds=75, limit=None):
        def go():
            conn = db.connect()
            rows = [dict(r) for r in queries.players(
                conn, _filters(f), sort=sort, min_rounds=min_rounds, limit=limit)]
            imgs = {r["id"]: dict(r) for r in conn.execute(
                "SELECT id, image_url, flag_url FROM players")}
            team_by_player = self._latest_teams(conn, [r["player_id"] for r in rows])
            for r in rows:
                p = imgs.get(r["player_id"]) or {}
                r["image_url"] = p.get("image_url")
                r["flag_url"] = p.get("flag_url")
                r["team_info"] = team_by_player.get(r["player_id"])
            return rows
        return self._wrap(go)

    def player_detail(self, player_id, f=None):
        def go():
            conn = db.connect()
            flt = _filters(f)
            meta = conn.execute(
                "SELECT id, ign, real_name, image_url, flag_url FROM players WHERE id=?",
                (player_id,)).fetchone()
            summary = queries.player_summary(conn, player_id, flt)
            by_map = [dict(r) for r in queries.player_by_map(conn, player_id, flt)]
            map_imgs = {r["name"]: r["image_url"] for r in conn.execute(
                "SELECT name, image_url FROM maps")}
            for r in by_map:
                r["image_url"] = map_imgs.get(r["map"])
            ops = {}
            icons = {r["name"]: r["icon_url"] for r in conn.execute(
                "SELECT name, icon_url FROM operators")}
            for side in ("atk", "def"):
                ops[side] = [dict(r) for r in queries.player_operators(
                    conn, player_id, flt, side)]
                for r in ops[side]:
                    r.update(op_icon(r["operator"], icons.get(r["operator"])))
            team = (self._latest_teams(conn, [player_id]) or {}).get(player_id)
            return {"meta": dict(meta) if meta else None,
                    "team": team,
                    "summary": dict(summary) if summary else None,
                    "by_map": by_map, "operators": ops}
        return self._wrap(go)

    def maps(self, f=None):
        def go():
            conn = db.connect()
            rows = [dict(r) for r in queries.maps(conn, _filters(f))]
            imgs = {r["name"]: r["image_url"] for r in conn.execute(
                "SELECT name, image_url FROM maps")}
            for r in rows:
                r["image_url"] = imgs.get(r["map"])
            return rows
        return self._wrap(go)

    def operators(self, f=None, side=None, sort="pick"):
        def go():
            conn = db.connect()
            rows, games = queries.operators(conn, _filters(f), side=side or None, sort=sort)
            icons = {r["name"]: r["icon_url"] for r in conn.execute(
                "SELECT name, icon_url FROM operators")}
            for r in rows:
                r.update(op_icon(r["operator"], icons.get(r["operator"])))
            return {"rows": rows, "games": games}
        return self._wrap(go)


    # ----- planning tab -----

    def plan_meta(self):
        def go():
            manifest = json.loads((WEB_DIR / "maps" / "maps.json").read_text())
            # blueprints are fetched, not vendored — show only what's on disk
            manifest = {
                name: e for name, e in manifest.items()
                if all((WEB_DIR / "maps" / e["slug"] / f"floor-{f['file']}.jpg").exists()
                       for f in e["floors"])
            }
            rooms_file = WEB_DIR / "maps" / "rooms.json"
            rooms = json.loads(rooms_file.read_text()) if rooms_file.exists() else {}
            conn = db.connect()
            ops = []
            for r in conn.execute(
                    "SELECT name, side, icon_url FROM operators ORDER BY name"):
                ops.append({"name": r["name"], "side": r["side"],
                            **op_icon(r["name"], r["icon_url"])})
            return {"maps": manifest, "operators": ops, "rooms": rooms}
        return self._wrap(go)

    @staticmethod
    def _plan_path(slug: str) -> Path:
        slug = re.sub(r"[^a-z0-9]", "", slug.lower())
        d = config.data_dir() / "plans"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{slug}.json"

    def plan_load(self, slug):
        def go():
            f = self._plan_path(slug)
            return json.loads(f.read_text()) if f.exists() else {}
        return self._wrap(go)

    def plan_save(self, slug, state):
        def go():
            self._plan_path(slug).write_text(json.dumps(state))
            return True
        return self._wrap(go)


def _claim_app_name(name: str) -> None:
    """Show `name` in the macOS menu bar instead of 'Python'."""
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info["CFBundleName"] = name
    except Exception:
        pass


def run():
    try:
        import webview
    except ImportError:
        raise SystemExit(
            "pywebview is not installed in this interpreter.\n"
            "Run the GUI with the project venv:  .venv/bin/python -m r6stats gui")
    _claim_app_name("R6 Pro Stats")
    webview.create_window(
        "R6 Pro Stats", url=str(WEB_DIR / "index.html"), js_api=JsApi(),
        width=1280, height=860, min_size=(980, 620), background_color="#0a1020")
    webview.start()
