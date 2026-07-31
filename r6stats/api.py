"""Minimal SiegeGG API client (stdlib only) with rate limiting and disk cache."""

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://siege.b-cdn.net"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 r6-pro-stats-cli"
)
RATE_LIMIT_SECONDS = 0.35
RETRIES = 3


class ApiError(Exception):
    pass


class Api:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0

    def _cache_path(self, path: str) -> Path:
        digest = hashlib.sha1(path.encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get_cached(self, path: str):
        """Return cached response for path, or None."""
        if not self.cache_dir:
            return None
        f = self._cache_path(path)
        if f.exists():
            try:
                return json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def put_cache(self, path: str, data) -> None:
        if self.cache_dir:
            self._cache_path(path).write_text(json.dumps(data, separators=(",", ":")))

    def get(self, path: str, use_cache: bool = False):
        """GET {BASE}{path}, returning parsed JSON."""
        if use_cache:
            cached = self.get_cached(path)
            if cached is not None:
                return cached

        wait = RATE_LIMIT_SECONDS - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        url = BASE + path
        last_err = None
        for attempt in range(RETRIES):
            self._last_request = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
                if use_cache:
                    self.put_cache(path, data)
                return data
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                last_err = e
                if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                    raise ApiError(f"404 for {url}") from e
                time.sleep(2 * (attempt + 1))
        raise ApiError(f"failed to fetch {url}: {last_err}")
