"""Fetch card art from issuer product pages (no RapidAPI)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

from credit_rewards.card_image import CARD_IMAGES_DIR, _guess_extension, _remove_other_variants, _stem
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.paths import data_dir

USER_AGENT = "Mozilla/5.0 (compatible; PayCue/0.1; +https://github.com/creditRewards)"
REFERENCE_CARDS_DIR = data_dir() / "reference" / "rewardscc" / "cards"
MANUAL_CATALOG_PATH = data_dir() / "card_catalog_manual.yaml"
IMAGE_SOURCES_PATH = data_dir() / "curated" / "card_image_sources.yaml"

_CARD_HINT = re.compile(r"card|credit|product|hero", re.I)


@lru_cache(maxsize=1)
def _registry_urls() -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in load_card_registry():
        url = str(entry.get("url") or "").strip()
        if url:
            out[str(entry["card_key"])] = url
    return out


@lru_cache(maxsize=1)
def _manual_urls() -> dict[str, str]:
    if not MANUAL_CATALOG_PATH.exists():
        return {}
    payload = yaml.safe_load(MANUAL_CATALOG_PATH.read_text()) or {}
    out: dict[str, str] = {}
    for row in payload.get("cards") or []:
        url = str(row.get("url") or "").strip()
        key = str(row.get("card_key") or "").strip()
        if key and url:
            out[key] = url
    return out


@lru_cache(maxsize=1)
def _source_overrides() -> dict[str, str]:
    if not IMAGE_SOURCES_PATH.exists():
        return {}
    payload = yaml.safe_load(IMAGE_SOURCES_PATH.read_text()) or {}
    return {str(k): str(v) for k, v in (payload.get("image_urls") or {}).items() if k and v}


def reference_product_url(card_key: str) -> str:
    path = REFERENCE_CARDS_DIR / f"{card_key}.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text())
        if isinstance(payload, list) and payload:
            return str(payload[0].get("cardUrl") or "").strip()
    except (json.JSONDecodeError, OSError, IndexError):
        return ""
    return ""


def product_url_from_db(card_key: str) -> str:
    try:
        from credit_rewards.datastore.db import session

        with session() as conn:
            row = conn.execute(
                "SELECT detail_json FROM cards WHERE card_key = ?",
                (card_key.strip(),),
            ).fetchone()
            if not row:
                return ""
            payload = json.loads(row["detail_json"])
            detail = payload[0] if isinstance(payload, list) and payload else payload
            if isinstance(detail, dict):
                return str(detail.get("cardUrl") or "").strip()
    except (ImportError, OSError, json.JSONDecodeError, TypeError, KeyError):
        return ""
    return ""


def product_url_for_card(card_key: str) -> str:
    key = card_key.strip()
    if not key:
        return ""
    for lookup in (_registry_urls, _manual_urls):
        url = lookup().get(key, "")
        if url:
            return url
    url = reference_product_url(key)
    if url:
        return url
    return product_url_from_db(key)


def resolve_official_image_url(card_key: str) -> str:
    """Scrape issuer product page; return HTTPS art URL (no file download)."""
    key = card_key.strip()
    if not key:
        return ""
    direct = _source_overrides().get(key, "")
    if direct.startswith(("http://", "https://")):
        return direct
    page_url = product_url_for_card(key)
    if not page_url:
        return ""
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(page_url)
            response.raise_for_status()
            return extract_card_image_url(response.text, str(response.url))
    except httpx.HTTPError:
        return ""


def _normalize_page_url(url: str, page_url: str) -> str:
    raw = url.strip()
    if not raw or raw.startswith("data:"):
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("/"):
        parsed = urlparse(page_url)
        return f"{parsed.scheme}://{parsed.netloc}{raw}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return urljoin(page_url, raw)


def _score_image(url: str, *, page_host: str) -> int:
    lower = url.lower()
    score = 0
    if _CARD_HINT.search(lower):
        score += 4
    if any(ext in lower for ext in (".webp", ".png", ".jpg", ".jpeg")):
        score += 2
    if "logo" in lower or "icon" in lower or "sprite" in lower:
        score -= 6
    if "share-image" in lower or "social" in lower or "favicon" in lower:
        score -= 10
    if "aexp-static.com" in lower and "cardasset" in lower:
        score += 8
    if "images.ctfassets.net" in lower or "/card-art/" in lower or "card_art" in lower:
        score += 8
    if page_host and page_host in lower:
        score += 1
    return score


def extract_card_image_url(html: str, page_url: str) -> str:
    for match in re.finditer(
        r"https://[^\s\"'<>]+aexp-static[^\s\"'<>]+/cardasset/images/[^\s\"'<>]+",
        html,
        re.I,
    ):
        url = match.group(0).rstrip("\\")
        if url:
            return url

    soup = BeautifulSoup(html, "html.parser")
    page_host = urlparse(page_url).netloc
    candidates: list[tuple[int, str]] = []

    for tag in soup.find_all("meta"):
        prop = (tag.get("property") or tag.get("name") or "").lower()
        if prop in {"og:image", "twitter:image"}:
            content = tag.get("content") or ""
            url = _normalize_page_url(content, page_url)
            if url:
                candidates.append((_score_image(url, page_host=page_host) + 3, url))

    for tag in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            url = _normalize_page_url(str(tag.get(attr) or ""), page_url)
            if not url:
                continue
            alt = str(tag.get("alt") or "")
            score = _score_image(url, page_host=page_host)
            if _CARD_HINT.search(alt):
                score += 3
            candidates.append((score, url))

    for tag in soup.find_all("source"):
        srcset = str(tag.get("srcset") or "")
        first = srcset.split(",")[0].strip().split()[0] if srcset else ""
        url = _normalize_page_url(first, page_url)
        if url:
            candidates.append((_score_image(url, page_host=page_host), url))

    if not candidates:
        return ""

    candidates.sort(key=lambda row: row[0], reverse=True)
    best_score, best_url = candidates[0]
    if best_score < 2:
        return ""
    return best_url


def download_image(card_key: str, image_url: str, *, dest_dir: Path | None = None) -> Path | None:
    out_dir = dest_dir or CARD_IMAGES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(image_url)
            response.raise_for_status()
            ext = _guess_extension(response.headers.get("content-type", ""), image_url)
            dest = out_dir / f"{_stem(card_key)}{ext}"
            dest.write_bytes(response.content)
            _remove_other_variants(card_key, dest)
            return dest
    except (httpx.HTTPError, OSError):
        return None


def fetch_official_card_image(
    card_key: str,
    *,
    dest_dir: Path | None = None,
    force: bool = False,
    product_url: str | None = None,
) -> Path | None:
    """Download card art from issuer site into data/card_images/."""
    from credit_rewards.card_image import local_image_path

    key = card_key.strip()
    if not key:
        return None
    if not force and local_image_path(key):
        return local_image_path(key)

    image_url = _source_overrides().get(key, "")
    if not image_url:
        page_url = (product_url or product_url_for_card(key)).strip()
        if not page_url:
            return None
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
                response = client.get(page_url)
                response.raise_for_status()
                image_url = extract_card_image_url(response.text, str(response.url))
        except httpx.HTTPError:
            return None

    if not image_url:
        return None
    return download_image(key, image_url, dest_dir=dest_dir)


def catalog_keys_with_product_url(catalog_rows: list[dict[str, Any]] | None = None) -> list[str]:
    from credit_rewards.card_catalog import load_catalog_index_all

    rows = catalog_rows if catalog_rows is not None else load_catalog_index_all()
    keys: list[str] = []
    for row in rows:
        key = str(row.get("card_key") or "").strip()
        if key and product_url_for_card(key):
            keys.append(key)
    return keys
