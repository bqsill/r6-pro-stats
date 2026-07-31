"""Fetch the official Ubisoft floor blueprints used by the planning tab.

These are Ubisoft's own assets, downloaded from their CDN on demand rather
than redistributed with this project. Each map page on ubisoft.com links the
same `blueprints.zip` this pulls.
"""

import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://ubistatic-a.ubisoft.com/0106/gamesites/rainbow6/blueprints/"

# slug -> zip filename (a couple differ from the plain pattern)
ZIPS = {
    "bank": "r6-maps-bank-blueprints.zip",
    "border": "r6-maps-border-blueprints.zip",
    "chalet": "r6-maps-chalet-blueprints.zip",
    "clubhouse": "r6-maps-clubhouse-blueprints.zip",
    "consulate": "r6-maps-consulate-blueprints_may23.zip",
    "fortress": "r6-maps-fortress-blueprints.zip",
    "kafe": "r6-maps-kafe-blueprints.zip",
    "lair": "r6-maps-lair-blueprints.zip",
    "nighthavenlabs": "r6-maps-nighthavenlabs-blueprints.zip",
    "skyscraper": "r6-maps-skyscraper-blueprints.zip",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def maps_dir() -> Path:
    return Path(__file__).resolve().parent / "web" / "maps"


def _upscale(data: bytes) -> bytes:
    """2x Lanczos + light sharpen, if Pillow is available.

    Ubisoft publishes these at 1600x900 only; upscaling keeps lines legible
    when zoomed. Without Pillow the originals are used as-is.
    """
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return data
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=45, threshold=3))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def fetch(force: bool = False, upscale: bool = True, verbose: bool = True) -> None:
    log = print if verbose else (lambda *a: None)
    root = maps_dir()
    manifest = json.loads((root / "maps.json").read_text())
    if upscale:
        try:
            import PIL  # noqa: F401
        except ImportError:
            log("note: Pillow not installed — keeping the original 1600x900 images\n"
                "      (pip install pillow, then re-run with --force, for 2x upscaling)\n")
            upscale = False

    for name, entry in manifest.items():
        slug = entry["slug"]
        dest = root / slug
        wanted = sorted({f["file"] for f in entry["floors"]})
        if not force and all((dest / f"floor-{n}.jpg").exists() for n in wanted):
            log(f"{name:16s} already present ({len(wanted)} floors)")
            continue

        url = BASE + ZIPS[slug]
        log(f"{name:16s} downloading...", end=" ", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            blob = resp.read()

        dest.mkdir(parents=True, exist_ok=True)
        written = 0
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for info in z.infolist():
                if "__MACOSX" in info.filename or not info.filename.endswith(".jpg"):
                    continue
                m = re.search(r"blueprint-(\d+)", Path(info.filename).name)
                if not m or int(m.group(1)) not in wanted:
                    continue
                data = z.read(info)
                if upscale:
                    data = _upscale(data)
                (dest / f"floor-{int(m.group(1))}.jpg").write_bytes(data)
                written += 1
        log(f"{written} floors")

    missing = [n for n, e in manifest.items()
               if not all((root / e["slug"] / f"floor-{f['file']}.jpg").exists()
                          for f in e["floors"])]
    if missing:
        log(f"\nincomplete: {', '.join(missing)}")
    else:
        log(f"\nall {len(manifest)} maps ready")
