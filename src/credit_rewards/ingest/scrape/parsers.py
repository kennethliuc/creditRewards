from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

# Standard category taxonomy (aligned with Rewards CC IDs where known)
CATEGORY_ALIASES: list[tuple[list[str], dict[str, Any]]] = [
    (
        ["grocery", "supermarket", "groceries", "u.s. supermarkets"],
        {
            "spendBonusCategoryId": 1132334901,
            "spendBonusCategoryName": "Grocery Stores",
            "spendBonusCategoryGroup": "Shopping",
            "spendBonusSubcategoryGroup": "Grocery",
        },
    ),
    (
        ["dining", "restaurant", "restaurants", "takeout", "delivery services"],
        {
            "spendBonusCategoryId": 160378660,
            "spendBonusCategoryName": "Dining",
            "spendBonusCategoryGroup": "Dining",
            "spendBonusSubcategoryGroup": "All Dining",
        },
    ),
    (
        ["amextravel.com", "amextravel", "american express travel", "amex travel"],
        {
            "spendBonusCategoryId": 1120466653,
            "spendBonusCategoryName": "amextravel.com",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Travel Agency",
            "_matchPriority": 10,
        },
    ),
    (
        ["travel purchased through chase", "chase travel", "travel portal"],
        {
            "spendBonusCategoryId": 900000101,
            "spendBonusCategoryName": "Travel",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "All Travel",
            "_matchPriority": 10,
        },
    ),
    (
        ["airfare", "flights", "airline", "airlines"],
        {
            "spendBonusCategoryId": 2013874334,
            "spendBonusCategoryName": "Airfare",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "All Airfare",
            "_matchPriority": 10,
        },
    ),
    (
        ["travel", "travel purchases"],
        {
            "spendBonusCategoryId": 164006704,
            "spendBonusCategoryName": "Travel",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "All Travel",
            "_matchPriority": 0,
        },
    ),
    (
        ["gas", "gas station", "fuel", "ev charging"],
        {
            "spendBonusCategoryId": 1455345350,
            "spendBonusCategoryName": "Gas Stations",
            "spendBonusCategoryGroup": "Auto",
            "spendBonusSubcategoryGroup": "All Gas Stations",
        },
    ),
    (
        ["streaming", "select streaming"],
        {
            "spendBonusCategoryId": 248970942,
            "spendBonusCategoryName": "Streaming Services",
            "spendBonusCategoryGroup": "Telecom",
            "spendBonusSubcategoryGroup": "Media",
        },
    ),
    (
        ["lyft"],
        {
            "spendBonusCategoryId": 606097,
            "spendBonusCategoryName": "Lyft",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Rideshare",
            "_matchPriority": 11,
        },
    ),
    (
        ["transit purchases", "on transit", "transit including"],
        {
            "spendBonusCategoryId": 1468589631,
            "spendBonusCategoryName": "Transit",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Transportation",
            "_matchPriority": 11,
        },
    ),
    (
        ["tolls", "toll", "parking"],
        {
            "spendBonusCategoryId": 11030576,
            "spendBonusCategoryName": "Tolls",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Transportation",
            "_matchPriority": 10,
        },
    ),
    (
        ["transit", "taxi", "rideshare", "trains", "buses"],
        {
            "spendBonusCategoryId": 1982334500,
            "spendBonusCategoryName": "Ridesharing",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Rideshare",
        },
    ),
    (
        ["uber"],
        {
            "spendBonusCategoryId": 1982334500,
            "spendBonusCategoryName": "Ridesharing",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Rideshare",
        },
    ),
    (
        ["drug", "pharmacies", "drugstores"],
        {
            "spendBonusCategoryId": 1096261883,
            "spendBonusCategoryName": "Drugstores",
            "spendBonusCategoryGroup": "Shopping",
            "spendBonusSubcategoryGroup": "Drugstores",
        },
    ),
    (
        ["entertainment", "capital one entertainment"],
        {
            "spendBonusCategoryId": 900000201,
            "spendBonusCategoryName": "Entertainment",
            "spendBonusCategoryGroup": "Entertainment",
            "spendBonusSubcategoryGroup": "All Entertainment",
        },
    ),
    (
        ["wholesale clubs", "wholesale club"],
        {
            "spendBonusCategoryId": 1386466601,
            "spendBonusCategoryName": "Wholesale Clubs",
            "spendBonusCategoryGroup": "Shopping",
            "spendBonusSubcategoryGroup": "Wholesale Club",
        },
    ),
    (
        ["fitness", "fitness clubs", "gym"],
        {
            "spendBonusCategoryId": 1576799624,
            "spendBonusCategoryName": "Fitness Clubs",
            "spendBonusCategoryGroup": "Services",
            "spendBonusSubcategoryGroup": "Health",
        },
    ),
    (
        ["home improvement", "home improvement and furnishings"],
        {
            "spendBonusCategoryId": 1550080980,
            "spendBonusCategoryName": "Home Improvement",
            "spendBonusCategoryGroup": "Shopping",
            "spendBonusSubcategoryGroup": "All Home Improvement",
        },
    ),
    (
        ["live entertainment"],
        {
            "spendBonusCategoryId": 929639080,
            "spendBonusCategoryName": "Live Entertainment",
            "spendBonusCategoryGroup": "Entertainment",
            "spendBonusSubcategoryGroup": "Live Entertainment",
        },
    ),
    (
        ["rent", "housing", "mortgage"],
        {
            "spendBonusCategoryId": 900000301,
            "spendBonusCategoryName": "Rent",
            "spendBonusCategoryGroup": "Payments",
            "spendBonusSubcategoryGroup": "Rent",
        },
    ),
    (
        ["telecom", "phone", "wireless", "internet"],
        {
            "spendBonusCategoryId": 1464813222,
            "spendBonusCategoryName": "Telecom",
            "spendBonusCategoryGroup": "Telecom",
            "spendBonusSubcategoryGroup": "All Telecom",
        },
    ),
    (
        ["rental cars", "car rentals booked", "rental cars booked"],
        {
            "spendBonusCategoryId": 670145462,
            "spendBonusCategoryName": "Car Rentals (Capital One)",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Car Rental",
            "_matchPriority": 12,
        },
    ),
    (
        ["hotels booked", "vacation rentals", "hotels, vacation rentals"],
        {
            "spendBonusCategoryId": 1517218866,
            "spendBonusCategoryName": "Hotels (Capital One)",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Hotels",
            "_matchPriority": 12,
        },
    ),
    (
        ["air travel booked", "flights booked through capital one"],
        {
            "spendBonusCategoryId": 1396855303,
            "spendBonusCategoryName": "Air Travel (Capital One)",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Airfare",
            "_matchPriority": 12,
        },
    ),
    (
        ["capital one entertainment", "entertainment purchases"],
        {
            "spendBonusCategoryId": 823114854,
            "spendBonusCategoryName": "Entertainment (Capital One)",
            "spendBonusCategoryGroup": "Entertainment",
            "spendBonusSubcategoryGroup": "Entertainment",
            "_matchPriority": 12,
        },
    ),
    (
        ["telecom", "phone plans"],
        {
            "spendBonusCategoryId": 1464813222,
            "spendBonusCategoryName": "Telecom",
            "spendBonusCategoryGroup": "Telecom",
            "spendBonusSubcategoryGroup": "Telecom",
        },
    ),
    (
        ["online shopping", "online retail", "u.s. online retail"],
        {
            "spendBonusCategoryId": 158645550,
            "spendBonusCategoryName": "Online Shopping",
            "spendBonusCategoryGroup": "Shopping",
            "spendBonusSubcategoryGroup": "Online Retail",
        },
    ),
    (
        ["citi travel", "booked with citi travel"],
        {
            "spendBonusCategoryId": 176638649,
            "spendBonusCategoryName": "Travel",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "All Travel",
            "_matchPriority": 11,
        },
    ),
    (
        ["flights booked through capital one travel", "flights booked with capital one travel"],
        {
            "spendBonusCategoryId": 1396855303,
            "spendBonusCategoryName": "Air Travel (Capital One)",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Travel Agency - Airfare",
            "_matchPriority": 13,
        },
    ),
    (
        ["rental cars booked through capital one travel", "rental cars booked with capital one travel"],
        {
            "spendBonusCategoryId": 670145462,
            "spendBonusCategoryName": "Car Rentals (Capital One)",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Travel Agency - Car Rental",
            "_matchPriority": 13,
        },
    ),
    (
        ["hotels booked through capital one travel", "hotels booked with capital one travel"],
        {
            "spendBonusCategoryId": 1517218866,
            "spendBonusCategoryName": "Hotels (Capital One)",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Travel Agency - Hotel",
            "_matchPriority": 13,
        },
    ),
]

CITI_CUSTOM_CASH_CATEGORIES: list[dict[str, Any]] = [
    {"spendBonusCategoryId": 160378660, "spendBonusCategoryName": "Dining", "spendBonusCategoryGroup": "Dining", "spendBonusSubcategoryGroup": "All Dining"},
    {"spendBonusCategoryId": 1096261883, "spendBonusCategoryName": "Drugstores", "spendBonusCategoryGroup": "Shopping", "spendBonusSubcategoryGroup": "All Drugstores"},
    {"spendBonusCategoryId": 1576799624, "spendBonusCategoryName": "Fitness Clubs", "spendBonusCategoryGroup": "Services", "spendBonusSubcategoryGroup": "Health"},
    {"spendBonusCategoryId": 1455345350, "spendBonusCategoryName": "Gas Stations", "spendBonusCategoryGroup": "Auto", "spendBonusSubcategoryGroup": "All Gas Stations"},
    {"spendBonusCategoryId": 1132334901, "spendBonusCategoryName": "Grocery Stores", "spendBonusCategoryGroup": "Shopping", "spendBonusSubcategoryGroup": "Grocery"},
    {"spendBonusCategoryId": 1550080980, "spendBonusCategoryName": "Home Improvement", "spendBonusCategoryGroup": "Shopping", "spendBonusSubcategoryGroup": "All Home Improvement"},
    {"spendBonusCategoryId": 929639080, "spendBonusCategoryName": "Live Entertainment", "spendBonusCategoryGroup": "Entertainment", "spendBonusSubcategoryGroup": "Live Entertainment"},
    {"spendBonusCategoryId": 248970942, "spendBonusCategoryName": "Streaming Services", "spendBonusCategoryGroup": "Telecom", "spendBonusSubcategoryGroup": "Media"},
    {"spendBonusCategoryId": 1468589631, "spendBonusCategoryName": "Transit", "spendBonusCategoryGroup": "Travel", "spendBonusSubcategoryGroup": "Transportation"},
    {"spendBonusCategoryId": 176638649, "spendBonusCategoryName": "Travel", "spendBonusCategoryGroup": "Travel", "spendBonusSubcategoryGroup": "All Travel"},
]

AMEX_CARD_MARKERS: dict[str, list[str]] = {
    "amex-gold": ["gold card", "american express® gold", "american express gold"],
    "amex-blue-cash-preferred": ["blue cash preferred"],
    "amex-platinum": ["platinum card", "the platinum card"],
    "amex-blue-business-plus": ["blue business plus"],
}

BOFA_CHOICE_CATEGORIES: list[dict[str, Any]] = [
    {"spendBonusCategoryId": 160378660, "spendBonusCategoryName": "Dining", "spendBonusCategoryGroup": "Dining", "spendBonusSubcategoryGroup": "All Dining"},
    {"spendBonusCategoryId": 1096261883, "spendBonusCategoryName": "Drugstores", "spendBonusCategoryGroup": "Shopping", "spendBonusSubcategoryGroup": "All Drugstores"},
    {"spendBonusCategoryId": 1455345350, "spendBonusCategoryName": "Gas Stations", "spendBonusCategoryGroup": "Auto", "spendBonusSubcategoryGroup": "All Gas Stations"},
    {"spendBonusCategoryId": 1550080980, "spendBonusCategoryName": "Home Improvement", "spendBonusCategoryGroup": "Shopping", "spendBonusSubcategoryGroup": "All Home Improvement"},
    {"spendBonusCategoryId": 158645550, "spendBonusCategoryName": "Online Shopping", "spendBonusCategoryGroup": "Shopping", "spendBonusSubcategoryGroup": "Online Retail"},
    {"spendBonusCategoryId": 248970942, "spendBonusCategoryName": "Streaming Services", "spendBonusCategoryGroup": "Telecom", "spendBonusSubcategoryGroup": "Media"},
    {"spendBonusCategoryId": 1464813222, "spendBonusCategoryName": "Telecom", "spendBonusCategoryGroup": "Telecom", "spendBonusSubcategoryGroup": "Telecom"},
    {"spendBonusCategoryId": 176638649, "spendBonusCategoryName": "Travel", "spendBonusCategoryGroup": "Travel", "spendBonusSubcategoryGroup": "All Travel"},
]

@dataclass
class ParsedEarnRule:
    multiplier: float
    description: str
    category_meta: dict[str, Any]
    spend_limit: float = 0
    spend_limit_reset_period: str = ""
    is_spend_limit: int = 0


def _html_inline_tag_text(html: str) -> str:
    """Extract visible copy from SPA markup when BeautifulSoup yields little text."""
    snippets: list[str] = []
    for tag in ("h1", "h2", "h3", "h4", "p", "li", "span"):
        for match in re.finditer(rf">([^<]{{4,240}})</{tag}>", html, re.I):
            text = re.sub(r"\s+", " ", match.group(1)).strip()
            if text and not text.startswith("{"):
                snippets.append(text)
    return " ".join(snippets)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    parts = [soup.get_text(" ", strip=True), _html_inline_tag_text(html), _html_embedded_reward_text(html)]
    text = " ".join(part for part in parts if part)
    return re.sub(r"\s+", " ", text)


def meta_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return str(tag["content"])
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        return str(og["content"])
    return ""


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def _html_embedded_reward_text(html: str) -> str:
    """Pull earn-rate phrases from SPA/JSON payloads not visible in html_to_text()."""
    import html as htmlmod

    normalized = (
        html.replace("\u003c", "<")
        .replace("\u003e", ">")
        .replace("\u0026", "&")
        .replace("\n", " ")
    )
    text = htmlmod.unescape(normalized)
    snippets: list[str] = []
    for match in re.finditer(r'content="([^"]{8,400})"', text):
        snippets.append(match.group(1))
    for match in re.finditer(r'"content"\s*:\s*"([^"]{8,400})"', text):
        snippets.append(match.group(1))
    for field in ("body", "headline", "title", "description", "text"):
        for match in re.finditer(rf'"{field}"\s*:\s*"([^"]{{8,400}})"', text):
            snippets.append(match.group(1))
    for match in re.finditer(
        r"(?:Earn\s+)?\d+(?:\.\d+)?\s*%\s*(?:cash back|Cash Back)[^\"\\]{5,160}",
        text,
        re.I,
    ):
        snippets.append(match.group(0))
    for match in re.finditer(
        r"\d+(?:\.\d+)?\s*[xX]\s*(?:miles|Miles|points|Points)[^\"\\]{5,160}",
        text,
        re.I,
    ):
        snippets.append(match.group(0))
    for match in re.finditer(
        r"\d+(?:\.\d+)?\s*miles per dollar[^\"\\]{5,120}",
        text,
        re.I,
    ):
        snippets.append(match.group(0))
    return " ".join(snippets)


def _parse_money_cap(fragment: str) -> tuple[float, str]:
    fragment_lower = fragment.lower()
    period = ""
    if "quarter" in fragment_lower:
        period = "Quarter"
    elif "year" in fragment_lower or "annual" in fragment_lower or "calendar year" in fragment_lower:
        period = "Year"

    match = re.search(r"up to \$?\s*([\d,]+)\s*([Kk])?", fragment, re.I)
    if not match:
        match = re.search(r"\$\s*([\d,]+)\s*([Kk])?", fragment, re.I)
    if not match:
        return 0.0, period

    amount = float(match.group(1).replace(",", ""))
    if match.group(2):
        amount *= 1000
    return amount, period


def _split_category_phrases(text: str) -> list[str]:
    parts = re.split(r"\s+&\s+|\s+and\s+", text, flags=re.I)
    return [p.strip(" ,.") for p in parts if p.strip()]


def _category_meta_for_output(meta: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in meta.items() if not k.startswith("_")}


def _match_category(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    best: tuple[int, int, dict[str, Any]] | None = None
    for aliases, meta in CATEGORY_ALIASES:
        priority = int(meta.get("_matchPriority", 0))
        for alias in aliases:
            if alias not in lowered:
                continue
            score = (priority, len(alias))
            if best is None or score > (best[0], best[1]):
                best = (priority, len(alias), _category_meta_for_output(meta))
    return best[2] if best else None


_FALLBACK_NOISE_PHRASES = (
    "membership rewards program",
    "terms and conditions",
    "card member agreement",
)


def _accept_fallback_segment(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 80 or "\\" in stripped:
        return False
    lowered = stripped.lower()
    if any(phrase in lowered for phrase in _FALLBACK_NOISE_PHRASES):
        return False
    if "eligible" in lowered and _match_category(stripped) is None:
        return False
    return True


def _fallback_category(text: str) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "other"
    cat_id = int(hashlib.md5(slug.encode()).hexdigest()[:8], 16)
    return {
        "spendBonusCategoryId": cat_id,
        "spendBonusCategoryName": text.strip()[:80],
        "spendBonusCategoryGroup": "Other",
        "spendBonusSubcategoryGroup": "Other",
    }


_EARN_CATEGORY_STOP = r"(?=\.|$|\s+Earn\s+\d|\s+\d+\s*[xX]\s)"

EARN_PATTERNS = [
    re.compile(
        r"(\d+(?:\.\d+)?)\s*[xX]\s*(?:Membership Rewards[^;]{0,40}|points|Points|miles|Miles)"
        r"\s*(?:on|at|for)\s+"
        r"((?:(?!\.\s*Earn\s+\d|\s+\d+\s*[xX]\s).){5,160}?)"
        + _EARN_CATEGORY_STOP,
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*[xX]\s*(?:miles|Miles)\s*(?:on|at|for)\s+([^.;]{3,120}?)"
        + _EARN_CATEGORY_STOP,
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:cash rewards|cash back|Cash Back|Daily Cash)\s*(?:on|at|for|when|back on)\s+([^.;]{3,120})",
        re.I,
    ),
    re.compile(
        r"earn\s+(\d+(?:\.\d+)?)\s*%\s*(?:Daily Cash|cash back|Cash Back)\s*(?:on|back on|at|for)\s+([^.;]{3,120})",
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:cash back|Cash Back|cash rewards)",
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*[xX]\s*(?:on|for)\s+(?:housing|rent|mortgage|everything else)",
        re.I,
    ),
    re.compile(
        r"up to\s+(\d+(?:\.\d+)?)\s*[xX]\s*(?:on|for)\s+(?:housing|rent)",
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*[xX]\s*(?:points|Points)\s*(?:on|for)\s+([^.;]{3,120}?)"
        + _EARN_CATEGORY_STOP,
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*[xX]\s*(?:miles|Miles)\s+on\s+(?:flights|hotels|rental cars)[^.;]{0,80}(?:capital one travel)",
        re.I,
    ),
    re.compile(
        r"earn\s+(?:unlimited\s+)?(\d+(?:\.\d+)?)\s*[xX]\s*miles\s+on\s+([^.;]{3,120}?capital one travel)",
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*[xX]\s*(?:miles|Miles)\b",
        re.I,
    ),
    re.compile(
        r"unlimited\s+(\d+(?:\.\d+)?)\s*%\s*(?:cash rewards|cash back)",
        re.I,
    ),
]


def _rule_from_meta(meta: dict[str, Any], *, multiplier: float, description: str) -> ParsedEarnRule:
    cap, period = _parse_money_cap(description)
    return ParsedEarnRule(
        multiplier=multiplier,
        description=description[:240],
        category_meta=meta,
        spend_limit=cap,
        spend_limit_reset_period=period,
        is_spend_limit=1 if cap > 0 else 0,
    )


def _upsert_rule(seen: dict[int, ParsedEarnRule], rule: ParsedEarnRule) -> None:
    cat_id = int(rule.category_meta["spendBonusCategoryId"])
    existing = seen.get(cat_id)
    if not existing or rule.multiplier > existing.multiplier:
        seen[cat_id] = rule


def _set_rule(seen: dict[int, ParsedEarnRule], rule: ParsedEarnRule) -> None:
    seen[int(rule.category_meta["spendBonusCategoryId"])] = rule


def _expand_chase_other_travel(text: str, seen: dict[int, ParsedEarnRule]) -> None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[xX×]\s*(?:points?\s+)?(?:on|for)\s+other travel(?:\s+purchases)?",
        text,
        re.I,
    )
    if not match:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*[xX×]\s*on\s+travel(?!\s+purchased)",
            text,
            re.I,
        )
    if not match:
        return
    _set_rule(
        seen,
        _rule_from_meta(
            {
                "spendBonusCategoryId": 176638649,
                "spendBonusCategoryName": "Travel",
                "spendBonusCategoryGroup": "Travel",
                "spendBonusSubcategoryGroup": "All Travel",
            },
            multiplier=float(match.group(1)),
            description=match.group(0).strip(),
        ),
    )


def _expand_citi_custom_cash(text: str, seen: dict[int, ParsedEarnRule]) -> None:
    if not re.search(r"top eligible spend category", text, re.I):
        return
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*%\s*cash back on your top eligible spend category",
        text,
        re.I,
    )
    if not match:
        return
    multiplier = float(match.group(1))
    desc = match.group(0)
    for meta in CITI_CUSTOM_CASH_CATEGORIES:
        _upsert_rule(seen, _rule_from_meta(meta, multiplier=multiplier, description=desc))


def _expand_bofa_customized_cash(text: str, seen: dict[int, ParsedEarnRule]) -> None:
    if "customized cash" not in text.lower() and "category of your choice" not in text.lower():
        return
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*%\s*cash back at grocery stores(?:,?\s*and now at wholesale clubs)?",
        text,
        re.I,
    ):
        mult = float(match.group(1))
        desc = match.group(0)
        for meta in (
            {
                "spendBonusCategoryId": 1132334901,
                "spendBonusCategoryName": "Grocery Stores",
                "spendBonusCategoryGroup": "Shopping",
                "spendBonusSubcategoryGroup": "Grocery",
            },
            {
                "spendBonusCategoryId": 1386466601,
                "spendBonusCategoryName": "Wholesale Clubs",
                "spendBonusCategoryGroup": "Shopping",
                "spendBonusSubcategoryGroup": "Wholesale Club",
            },
        ):
            _upsert_rule(seen, _rule_from_meta(meta, multiplier=mult, description=desc))
    choice_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*cash back on gas", text, re.I)
    if choice_match:
        mult = float(choice_match.group(1))
        desc = choice_match.group(0)
        for meta in BOFA_CHOICE_CATEGORIES:
            _upsert_rule(seen, _rule_from_meta(meta, multiplier=mult, description=desc))


def _expand_amex_transit_bundle(text: str, seen: dict[int, ParsedEarnRule]) -> None:
    if not re.search(r"(\d+(?:\.\d+)?)\s*%\s*cash back on transit", text, re.I):
        return
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*cash back on transit", text, re.I)
    if not match:
        return
    mult = float(match.group(1))
    desc = match.group(0)
    for meta in (
        {
            "spendBonusCategoryId": 1468589631,
            "spendBonusCategoryName": "Transit",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Transportation",
        },
        {
            "spendBonusCategoryId": 11030576,
            "spendBonusCategoryName": "Tolls",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Transportation",
        },
        {
            "spendBonusCategoryId": 1982334500,
            "spendBonusCategoryName": "Ridesharing",
            "spendBonusCategoryGroup": "Travel",
            "spendBonusSubcategoryGroup": "Rideshare",
        },
    ):
        _upsert_rule(seen, _rule_from_meta(meta, multiplier=mult, description=desc))
    gas_match = re.search(
        r"(\d+(?:\.\d+)?)\s*%\s*cash back(?:\s+at)?\s+u\.?s\.?\s+gas stations",
        text,
        re.I,
    )
    if gas_match:
        _upsert_rule(
            seen,
            _rule_from_meta(
                {
                    "spendBonusCategoryId": 1455345350,
                    "spendBonusCategoryName": "Gas Stations",
                    "spendBonusCategoryGroup": "Auto",
                    "spendBonusSubcategoryGroup": "All Gas Stations",
                },
                multiplier=float(gas_match.group(1)),
                description=gas_match.group(0),
            ),
        )


def _expand_capital_one_travel_showcase(
    html: str,
    seen: dict[int, ParsedEarnRule],
    card_key: str | None = None,
) -> None:
    blob = f"{meta_description(html)} {_html_embedded_reward_text(html)}".lower()
    if "capital one travel" not in blob and "showcase-" not in html.lower():
        return
    if re.search(r"showcase-5x|showcase-5X", html):
        _upsert_rule(
            seen,
            _rule_from_meta(
                {
                    "spendBonusCategoryId": 1396855303,
                    "spendBonusCategoryName": "Air Travel (Capital One)",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "Travel Agency - Airfare",
                },
                multiplier=5.0,
                description="5X Miles on flights booked through Capital One Travel",
            ),
        )
    if re.search(r"showcase-10x|showcase-10X", html):
        for meta, label in (
            (
                {
                    "spendBonusCategoryId": 1517218866,
                    "spendBonusCategoryName": "Hotels (Capital One)",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "Travel Agency - Hotel",
                },
                "hotels",
            ),
            (
                {
                    "spendBonusCategoryId": 670145462,
                    "spendBonusCategoryName": "Car Rentals (Capital One)",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "Travel Agency - Car Rental",
                },
                "rental cars",
            ),
        ):
            if label in blob:
                _upsert_rule(
                    seen,
                    _rule_from_meta(
                        meta,
                        multiplier=10.0,
                        description=f"10X Miles on {label} booked through Capital One Travel",
                    ),
                )
    if card_key and "savor" in card_key and re.search(r"showcase-5x|showcase-5X", html):
        for meta, label in (
            (
                {
                    "spendBonusCategoryId": 1517218866,
                    "spendBonusCategoryName": "Hotels (Capital One)",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "Travel Agency - Hotel",
                },
                "hotels",
            ),
            (
                {
                    "spendBonusCategoryId": 670145462,
                    "spendBonusCategoryName": "Car Rentals (Capital One)",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "Travel Agency - Car Rental",
                },
                "rental cars",
            ),
        ):
            _upsert_rule(
                seen,
                _rule_from_meta(
                    meta,
                    multiplier=5.0,
                    description=f"5X miles on {label} booked through Capital One Travel",
                ),
            )


def _expand_bilt_lyft(html: str, seen: dict[int, ParsedEarnRule]) -> None:
    text = html_to_text(html)
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[xX×]\s*(?:points|pts)\s*(?:on|for)\s+lyft",
        text,
        re.I,
    )
    mult: float | None = float(match.group(1)) if match else None
    if mult is None and "lyft" in html.lower():
        mults = [
            float(m.group(1))
            for m in re.finditer(
                r"(?:up to\s+)?(\d+(?:\.\d+)?)\s*[xX×]\s*(?:points|pts)",
                html,
                re.I,
            )
        ]
        if mults:
            mult = max(mults)
    if mult is None:
        best_mult: float | None = None
        for anchor in re.finditer(
            r'(?:data-framer-name="Lyft"|Ride with Lyft|>Lyft<|>Lyft</)',
            html,
            re.I,
        ):
            window = html[max(0, anchor.start() - 1200) : anchor.end() + 1200]
            if "lyftapi" in window.lower():
                continue
            for near in re.finditer(
                r"(?:up to\s+)?(\d+(?:\.\d+)?)\s*[xX×]\s*(?:points|pts)",
                window,
                re.I,
            ):
                candidate = float(near.group(1))
                if best_mult is None or candidate > best_mult:
                    best_mult = candidate
        mult = best_mult
    if mult is None:
        return
    _upsert_rule(
        seen,
        _rule_from_meta(
            {
                "spendBonusCategoryId": 606097,
                "spendBonusCategoryName": "Lyft",
                "spendBonusCategoryGroup": "Travel",
                "spendBonusSubcategoryGroup": "Rideshare",
            },
            multiplier=mult,
            description=f"{mult:g}X points on Lyft rides",
        ),
    )


def _is_choice_category_rule(rule: ParsedEarnRule) -> bool:
    desc = rule.description.lower()
    return "top eligible spend category" in desc or "choice category" in desc


def _expand_amex_card_earn(html: str, card_key: str, seen: dict[int, ParsedEarnRule]) -> None:
    """Seed earn rules from card-specific meta/body copy on noisy Amex SPA pages."""
    desc = meta_description(html)
    blob = " ".join([desc, html_to_text(html), _html_embedded_reward_text(html)])
    if card_key == "amex-gold":
        if desc:
            restaurant_match = re.search(
                r"(\d+(?:\.\d+)?)\s*[xX×]\s*points?\s*(?:on|at)\s+restaurants",
                desc,
                re.I,
            )
            if restaurant_match:
                _set_rule(
                    seen,
                    _rule_from_meta(
                        {
                            "spendBonusCategoryId": 160378660,
                            "spendBonusCategoryName": "Dining",
                            "spendBonusCategoryGroup": "Dining",
                            "spendBonusSubcategoryGroup": "All Dining",
                        },
                        multiplier=float(restaurant_match.group(1)),
                        description=restaurant_match.group(0).strip(),
                    ),
                )
            market_match = re.search(
                r"(\d+(?:\.\d+)?)\s*[xX×]\s*points?.*?supermarkets",
                desc,
                re.I,
            )
            if market_match:
                _set_rule(
                    seen,
                    _rule_from_meta(
                        {
                            "spendBonusCategoryId": 1132334901,
                            "spendBonusCategoryName": "Grocery Stores",
                            "spendBonusCategoryGroup": "Shopping",
                            "spendBonusSubcategoryGroup": "Grocery",
                        },
                        multiplier=float(market_match.group(1)),
                        description=desc.strip(),
                    ),
                )
        gold_blob = " ".join(_filter_chunks_for_card([blob], card_key))
        for pattern, meta in (
            (
                re.compile(
                    r"3\s*[xX×]\s*points.{0,30}on flights booked directly with airlines",
                    re.I,
                ),
                {
                    "spendBonusCategoryId": 2013874334,
                    "spendBonusCategoryName": "Airfare",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "All Airfare",
                },
            ),
            (
                re.compile(
                    r"2\s*[xX×]\s*points.{0,30}on prepaid hotels booked through amextravel",
                    re.I,
                ),
                {
                    "spendBonusCategoryId": 1120466653,
                    "spendBonusCategoryName": "amextravel.com",
                    "spendBonusCategoryGroup": "Travel",
                    "spendBonusSubcategoryGroup": "Travel Agency",
                },
            ),
        ):
            hit = pattern.search(gold_blob)
            if hit:
                _set_rule(
                    seen,
                    _rule_from_meta(
                        meta,
                        multiplier=3.0 if meta["spendBonusCategoryId"] == 2013874334 else 2.0,
                        description=hit.group(0).strip(),
                    ),
                )
        return
    elif card_key == "amex-blue-cash-preferred":
        blue_blob = " ".join(_filter_chunks_for_card([desc, html_to_text(html)], card_key))
        for pattern, meta in (
            (
                re.compile(r"(\d+(?:\.\d+)?)\s*%\s*cash back at u\.?s\.?\s+supermarkets", re.I),
                {
                    "spendBonusCategoryId": 1132334901,
                    "spendBonusCategoryName": "Grocery Stores",
                    "spendBonusCategoryGroup": "Shopping",
                    "spendBonusSubcategoryGroup": "Grocery",
                },
            ),
            (
                re.compile(r"(\d+(?:\.\d+)?)\s*%\s*cash back on select u\.?s\.?\s+streaming", re.I),
                {
                    "spendBonusCategoryId": 248970942,
                    "spendBonusCategoryName": "Streaming Services",
                    "spendBonusCategoryGroup": "Telecom",
                    "spendBonusSubcategoryGroup": "Media",
                },
            ),
            (
                re.compile(r"(\d+(?:\.\d+)?)\s*%\s*cash back at u\.?s\.?\s+gas stations", re.I),
                {
                    "spendBonusCategoryId": 1455345350,
                    "spendBonusCategoryName": "Gas Stations",
                    "spendBonusCategoryGroup": "Auto",
                    "spendBonusSubcategoryGroup": "All Gas Stations",
                },
            ),
        ):
            hits = [float(m.group(1)) for m in pattern.finditer(blue_blob)]
            if not hits:
                continue
            mult = max(hits)
            _set_rule(
                seen,
                _rule_from_meta(
                    meta,
                    multiplier=mult,
                    description=f"{mult:g}% cash back at U.S. {meta['spendBonusCategoryName'].lower()}",
                ),
            )
        return


def _filter_chunks_for_card(chunks: list[str], card_key: str | None) -> list[str]:
    if not card_key:
        return chunks
    markers = AMEX_CARD_MARKERS.get(card_key)
    if not markers:
        return chunks
    filtered: list[str] = []
    for chunk in chunks:
        lowered = chunk.lower()
        if any(marker in lowered for marker in markers):
            filtered.append(chunk)
    return filtered or chunks


def _prune_noise_rules(seen: dict[int, ParsedEarnRule]) -> None:
    noise_terms = (
        "delta",
        "marriott",
        "hilton",
        "bonvoy",
        "sky miles",
        "select u",
        "the rest of the year",
    )
    drop_ids: list[int] = []
    for cat_id, rule in seen.items():
        name = rule.category_meta.get("spendBonusCategoryName", "").lower()
        if "(capital one)" in name:
            continue
        if name == "all purchases" and rule.multiplier >= 5.0:
            drop_ids.append(cat_id)
        if "eligible u" in name or name.endswith(" at u"):
            drop_ids.append(cat_id)
        if "first year" in rule.description.lower() and rule.multiplier >= 6.0:
            drop_ids.append(cat_id)
        if any(term in name for term in noise_terms):
            drop_ids.append(cat_id)
        if "<" in name or "sup" in name:
            drop_ids.append(cat_id)
        if not _is_choice_category_rule(rule):
            if name == "gas stations" and rule.multiplier > 3.5:
                drop_ids.append(cat_id)
            if name == "dining" and rule.multiplier > 4.5:
                drop_ids.append(cat_id)
            if name == "grocery stores" and rule.multiplier > 6.5:
                drop_ids.append(cat_id)
        if name == "amextravel.com" and rule.multiplier > 3.0:
            drop_ids.append(cat_id)
        if name == "airfare" and rule.multiplier > 5.0:
            drop_ids.append(cat_id)
    for cat_id in drop_ids:
        seen.pop(cat_id, None)


def _collect_earn_rules(chunks: list[str], *, allow_bare_multipliers: bool) -> list[ParsedEarnRule]:
    bare_idxs = {4, 5, 6, 10}
    seen: dict[int, ParsedEarnRule] = {}

    for chunk in chunks:
        if not chunk:
            continue
        for idx, pattern in enumerate(EARN_PATTERNS):
            if not allow_bare_multipliers and idx in bare_idxs:
                continue
            for match in pattern.finditer(chunk):
                multiplier = float(match.group(1))
                if match.lastindex and match.lastindex >= 2 and match.group(2):
                    category_text = match.group(2).strip()
                elif "housing" in match.group(0).lower() or "rent" in match.group(0).lower():
                    category_text = "rent and housing"
                else:
                    category_text = "all purchases"
                if category_text == "all purchases" and not allow_bare_multipliers:
                    continue
                full_desc = match.group(0).strip()
                cap, period = _parse_money_cap(full_desc)

                segments = _split_category_phrases(category_text) or [category_text]
                for segment in segments:
                    meta = _match_category(segment) or _match_category(full_desc)
                    if not meta:
                        if not _accept_fallback_segment(segment):
                            continue
                        meta = _fallback_category(segment)

                    rule = ParsedEarnRule(
                        multiplier=multiplier,
                        description=full_desc[:240],
                        category_meta=meta,
                        spend_limit=cap,
                        spend_limit_reset_period=period,
                        is_spend_limit=1 if cap > 0 else 0,
                    )
                    cat_id = int(meta["spendBonusCategoryId"])
                    existing = seen.get(cat_id)
                    if not existing or rule.multiplier > existing.multiplier:
                        seen[cat_id] = rule

    return list(seen.values())


def extract_earn_rules(html: str, card_key: str | None = None) -> list[ParsedEarnRule]:
    chunks = _filter_chunks_for_card(
        [
            meta_description(html),
            html_to_text(html),
            _html_inline_tag_text(html),
            _html_embedded_reward_text(html),
        ],
        card_key,
    )
    seen = {int(r.category_meta["spendBonusCategoryId"]): r for r in _collect_earn_rules(chunks, allow_bare_multipliers=False)}
    blob = " ".join(chunks)
    custom_cash_before = len(seen)
    _expand_citi_custom_cash(blob, seen)
    if len(seen) > custom_cash_before:
        seen.pop(900000301, None)
    _expand_bofa_customized_cash(blob, seen)
    _expand_amex_transit_bundle(blob, seen)
    _prune_noise_rules(seen)
    _expand_chase_other_travel(blob, seen)
    if card_key and card_key.startswith("amex-"):
        _expand_amex_card_earn(html, card_key, seen)
    _expand_capital_one_travel_showcase(html, seen, card_key=card_key)
    _expand_bilt_lyft(html, seen)
    return list(seen.values())


def rules_to_spend_bonus_category(rules: list[ParsedEarnRule]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for rule in rules:
        meta = rule.category_meta
        payload.append(
            {
                "spendBonusCategoryType": f"Single Category - {meta['spendBonusCategoryName']}",
                "spendBonusCategoryName": meta["spendBonusCategoryName"],
                "spendBonusCategoryId": meta["spendBonusCategoryId"],
                "spendBonusCategoryGroup": meta.get("spendBonusCategoryGroup", "Other"),
                "spendBonusSubcategoryGroup": meta.get("spendBonusSubcategoryGroup", "Other"),
                "spendBonusDesc": rule.description,
                "earnMultiplier": rule.multiplier,
                "isDateLimit": 0,
                "limitBeginDate": "",
                "limitEndDate": "",
                "isSpendLimit": rule.is_spend_limit,
                "spendLimit": rule.spend_limit,
                "spendLimitResetPeriod": rule.spend_limit_reset_period,
            }
        )
    return payload
