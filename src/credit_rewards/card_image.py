"""Card art: bundled data/card_images/ (primary) + URL manifest fallback + SVG placeholder."""

from __future__ import annotations

import json
import mimetypes
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from credit_rewards.card_catalog import resolve_wallet_card_key
from credit_rewards.paths import data_dir

IMAGE_URLS_PATH = data_dir() / "curated" / "card_image_urls.yaml"
IMAGE_SOURCES_PATH = data_dir() / "curated" / "card_image_sources.yaml"
CARD_IMAGES_DIR = data_dir() / "card_images"
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_ISSUER_COLORS = {
    "chase": "#117ACA",
    "american express": "#006FCF",
    "amex": "#006FCF",
    "citi": "#003B70",
    "capital one": "#D03027",
    "discover": "#FF6000",
    "wells fargo": "#D71E28",
    "bank of america": "#E31837",
    "goldman sachs": "#7399C6",
    "barclays": "#00AEEF",
    "u.s. bank": "#0C2074",
    "us bank": "#0C2074",
    "synchrony": "#F04E23",
    "comenity": "#512B7E",
    "keybank": "#009639",
    "santander": "#EC0000",
}


def _stem(card_key: str) -> str:
    return re.sub(r"[^\w\-.]", "_", card_key.strip()) or "card"


def _image_dir() -> Path:
    return CARD_IMAGES_DIR


def local_image_path(card_key: str) -> Path | None:
    """Path to bundled image file in data/card_images/, if present."""
    resolved = resolve_wallet_card_key(card_key)
    for key in (str(resolved["card_key"]), card_key.strip()):
        if not key:
            continue
        stem = _stem(key)
        for ext in _IMAGE_EXTENSIONS:
            path = _image_dir() / f"{stem}{ext}"
            if path.is_file() and path.stat().st_size > 0:
                return path
    return None


def local_image_serve_url(card_key: str) -> str:
    resolved = resolve_wallet_card_key(card_key)
    return f"/api/cards/image/file?card_key={quote(str(resolved['card_key']).strip(), safe='')}"


def placeholder_image_url(card_key: str) -> str:
    resolved = resolve_wallet_card_key(card_key)
    key = quote(str(resolved["card_key"]).strip(), safe="")
    return f"/api/cards/image/placeholder?card_key={key}"


@lru_cache(maxsize=1)
def load_image_url_manifest() -> dict[str, str]:
    merged: dict[str, str] = {}
    if IMAGE_URLS_PATH.exists():
        try:
            payload = yaml.safe_load(IMAGE_URLS_PATH.read_text()) or {}
            for key, url in (payload.get("urls") or {}).items():
                if key and url:
                    merged[str(key)] = str(url)
        except (OSError, yaml.YAMLError):
            pass
    if IMAGE_SOURCES_PATH.exists():
        try:
            payload = yaml.safe_load(IMAGE_SOURCES_PATH.read_text()) or {}
            for key, url in (payload.get("image_urls") or {}).items():
                if key and url:
                    merged.setdefault(str(key), str(url))
        except (OSError, yaml.YAMLError):
            pass
    return merged


def clear_image_url_manifest_cache() -> None:
    load_image_url_manifest.cache_clear()


def _lookup_manifest_url(card_key: str, resolved: dict[str, Any] | None = None) -> str:
    manifest = load_image_url_manifest()
    key = card_key.strip()
    if not key:
        return ""
    if key in manifest:
        return manifest[key]
    resolved = resolved or resolve_wallet_card_key(key)
    wallet_key = str(resolved["card_key"])
    rc_key = str(resolved["rewards_cc_card_key"])
    return manifest.get(wallet_key) or manifest.get(rc_key) or ""


def _scrape_official_image_url(card_key: str) -> str:
    from credit_rewards.ingest.card_image_fetch import resolve_official_image_url

    return resolve_official_image_url(card_key)


def resolve_card_image_url(card_key: str, *, allow_scrape: bool = True) -> str:
    """HTTPS issuer CDN, optional dev file, or SVG placeholder — always non-empty."""
    key = card_key.strip()
    if not key:
        return placeholder_image_url("card")

    resolved = resolve_wallet_card_key(key)
    wallet_key = str(resolved["card_key"])

    if local_image_path(key):
        return local_image_serve_url(wallet_key)

    manifest_url = _lookup_manifest_url(key, resolved)
    if manifest_url.startswith(("http://", "https://")):
        return manifest_url

    if allow_scrape:
        scraped = _scrape_official_image_url(wallet_key)
        if scraped.startswith(("http://", "https://")):
            return scraped

    existing = str(resolved.get("image_url") or "")
    if existing.startswith(("http://", "https://")):
        return existing

    return placeholder_image_url(wallet_key)


def resolve_card_image_urls(card_keys: list[str]) -> dict[str, str]:
    return {
        k.strip(): resolve_card_image_url(k, allow_scrape=False)
        for k in card_keys
        if k and k.strip()
    }


def card_image_url_for_display(card_key: str) -> str:
    return resolve_card_image_url(card_key)


def apply_local_image_urls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        key = str(row.get("card_key") or "")
        row["image_url"] = card_image_url_for_display(key)
    return rows


def apply_manifest_image_urls(rows: dict[str, dict[str, Any]]) -> int:
    manifest = load_image_url_manifest()
    applied = 0
    for row in rows.values():
        wallet_key = str(row.get("card_key") or "")
        rc_key = str(row.get("rewards_cc_card_key") or "")
        url = manifest.get(wallet_key) or manifest.get(rc_key) or ""
        if url and not str(row.get("image_url") or ""):
            row["image_url"] = url
            applied += 1
    return applied


def bundled_image_count() -> int:
    if not CARD_IMAGES_DIR.is_dir():
        return 0
    return sum(
        1
        for path in CARD_IMAGES_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS and path.stat().st_size > 0
    )


def manifest_image_count() -> int:
    return len(load_image_url_manifest())


def registry_card_keys_for_images() -> list[str]:
    from credit_rewards.ingest.scrape.registry import load_card_registry

    return [str(entry["card_key"]) for entry in load_card_registry()]


def _guess_extension(content_type: str, remote_url: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct == "image/webp":
        return ".webp"
    if ct == "image/gif":
        return ".gif"
    path = remote_url.split("?", 1)[0].lower()
    for ext in _IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return ".jpg"


def _remove_other_variants(card_key: str, keep: Path) -> None:
    stem = _stem(card_key)
    for ext in _IMAGE_EXTENSIONS:
        path = _image_dir() / f"{stem}{ext}"
        if path != keep and path.exists():
            path.unlink(missing_ok=True)


def issuer_color(issuer: str) -> str:
    norm = (issuer or "").strip().lower()
    for token, color in _ISSUER_COLORS.items():
        if token in norm:
            return color
    return "#0D9488"


def render_placeholder_svg(card_key: str) -> str:
    resolved = resolve_wallet_card_key(card_key)
    name = str(resolved.get("card_name") or card_key).replace("-", " ")
    issuer = str(resolved.get("issuer") or "")
    color = issuer_color(issuer)
    label = re.sub(r"[^A-Za-z0-9 ]", "", name).strip()[:28] or card_key[:20]
    words = label.split()
    line1 = " ".join(words[:3]) if words else label[:16]
    line2 = " ".join(words[3:6]) if len(words) > 3 else ""
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    y2 = ' y="58"' if line2 else ""
    t2 = f'<text x="16"{y2} fill="#ffffff" font-family="system-ui,sans-serif" font-size="11" opacity="0.92">{esc(line2)}</text>' if line2 else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="304" viewBox="0 0 480 304" role="img" aria-label="{esc(name)}">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{color}"/><stop offset="100%" stop-color="#111827"/></linearGradient></defs>
  <rect width="480" height="304" rx="18" fill="url(#g)"/>
  <text x="16" y="36" fill="#ffffff" font-family="system-ui,sans-serif" font-size="13" font-weight="700" opacity="0.95">{esc(issuer[:32] or "Card")}</text>
  <text x="16" y="78" fill="#ffffff" font-family="system-ui,sans-serif" font-size="11" opacity="0.92">{esc(line1)}</text>
  {t2}
</svg>"""


def media_type_for_card_image(card_key: str) -> str:
    path = local_image_path(card_key)
    if not path:
        return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"
