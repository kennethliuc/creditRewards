"""Card art: Rewards CC API + on-disk cache served from this app."""

from __future__ import annotations

import json
import mimetypes
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from credit_rewards.card_catalog import resolve_wallet_card_key
from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.paths import data_dir

IMAGE_CACHE_PATH = data_dir() / "card_image_cache.json"
CARD_IMAGES_DIR = data_dir() / "card_images"
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _stem(card_key: str) -> str:
    return re.sub(r"[^\w\-.]", "_", card_key.strip()) or "card"


def _image_dir() -> Path:
    CARD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return CARD_IMAGES_DIR


def local_image_path(card_key: str) -> Path | None:
    """Path to a cached image file, if present."""
    stem = _stem(card_key)
    for ext in _IMAGE_EXTENSIONS:
        path = _image_dir() / f"{stem}{ext}"
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def local_image_serve_url(card_key: str) -> str:
    return f"/api/cards/image/file?card_key={quote(card_key.strip(), safe='')}"


def card_image_url_for_display(card_key: str) -> str:
    """Immediate URL for API/UI when a local file exists."""
    key = card_key.strip()
    if not key:
        return ""
    resolved = resolve_wallet_card_key(key)
    wallet_key = str(resolved["card_key"])
    if local_image_path(wallet_key):
        return local_image_serve_url(wallet_key)
    return ""


def apply_local_image_urls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        key = str(row.get("card_key") or "")
        url = card_image_url_for_display(key)
        if url:
            row["image_url"] = url
    return rows


def _load_cache() -> dict[str, str]:
    if not IMAGE_CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(IMAGE_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(k): str(v) for k, v in (payload or {}).items() if v}


def _save_cache(cache: dict[str, str]) -> None:
    IMAGE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n")


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


def _download_to_local(card_key: str, remote_url: str) -> Path | None:
    if not remote_url.startswith(("http://", "https://")):
        return None
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(remote_url)
            response.raise_for_status()
            ext = _guess_extension(
                response.headers.get("content-type", ""),
                remote_url,
            )
            dest = _image_dir() / f"{_stem(card_key)}{ext}"
            dest.write_bytes(response.content)
            _remove_other_variants(card_key, dest)
            return dest
    except (httpx.HTTPError, OSError):
        return None


def _remote_image_url(
    wallet_key: str,
    resolved: dict[str, Any],
    *,
    client: CardDataClient | None = None,
) -> str:
    cached = _load_cache()
    if wallet_key in cached:
        return cached[wallet_key]

    existing = str(resolved.get("image_url") or "")
    if existing.startswith(("http://", "https://")):
        cached[wallet_key] = existing
        _save_cache(cached)
        return existing

    api = client or CardDataClient(use_local=False)
    if not api.is_configured:
        return ""

    rc_key = str(resolved["rewards_cc_card_key"])
    url = ""
    try:
        payload = api.get(f"creditcard-card-image/{rc_key}")
        if isinstance(payload, list) and payload:
            url = str(payload[0].get("cardImageUrl") or "")
    except RewardsCCError:
        url = ""

    cached[wallet_key] = url
    _save_cache(cached)
    return url


def ensure_local_card_image(
    card_key: str,
    *,
    client: CardDataClient | None = None,
) -> str:
    """Fetch remote art if needed, save under data/card_images/, return serve URL."""
    resolved = resolve_wallet_card_key(card_key)
    wallet_key = str(resolved["card_key"])
    if local_image_path(wallet_key):
        return local_image_serve_url(wallet_key)

    remote = _remote_image_url(wallet_key, resolved, client=client)
    if remote and _download_to_local(wallet_key, remote):
        return local_image_serve_url(wallet_key)
    return remote


def fetch_card_image_url(card_key: str, *, client: CardDataClient | None = None) -> str:
    """Return local serve URL when cached; otherwise fetch, save, and return."""
    return ensure_local_card_image(card_key, client=client)


def fetch_card_image_urls(
    card_keys: list[str],
    *,
    client: CardDataClient | None = None,
) -> dict[str, str]:
    api = client or CardDataClient(use_local=False)
    out: dict[str, str] = {}
    for key in card_keys:
        k = key.strip()
        if not k:
            continue
        out[k] = fetch_card_image_url(k, client=api)
    return out


def registry_card_keys_for_images() -> list[str]:
    from credit_rewards.ingest.scrape.registry import load_card_registry

    return [str(entry["card_key"]) for entry in load_card_registry()]


def warm_card_images(
    card_keys: list[str],
    *,
    client: CardDataClient | None = None,
    sleep_seconds: float = 0.05,
) -> dict[str, str]:
    """Download missing images for the given card keys."""
    api = client or CardDataClient(use_local=False)
    out: dict[str, str] = {}
    for key in card_keys:
        k = key.strip()
        if not k:
            continue
        out[k] = ensure_local_card_image(k, client=api)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return out


def warm_registry_card_images(*, client: CardDataClient | None = None) -> dict[str, str]:
    """Prefetch art for Phase-1 registry (popular) cards."""
    keys = registry_card_keys_for_images()
    missing = [k for k in keys if not local_image_path(k)]
    if not missing:
        return {k: local_image_serve_url(k) for k in keys if local_image_path(k)}
    return warm_card_images(missing, client=client)


def media_type_for_card_image(card_key: str) -> str:
    path = local_image_path(card_key)
    if not path:
        return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"
