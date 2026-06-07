from __future__ import annotations

import re
from dataclasses import dataclass, field

from credit_rewards.ingest.scrape.parsers import html_to_text

SNIPPET_RADIUS = 140
MULTIPLIER_PATTERN = r"(?:up to\s+)?(\d+(?:\.\d+)?)\s*(?:x|X|×|times|%|percent)"

# Search terms on issuer page text, keyed by normalized category hints.
CATEGORY_SEARCH_TERMS: dict[str, list[str]] = {
    "airfare": ["flight", "flights", "airline", "airfare", "airlines"],
    "dining": ["dining", "restaurant", "restaurants", "takeout", "delivery"],
    "grocery stores": ["grocery", "groceries", "supermarket", "supermarkets"],
    "amextravel.com": ["amextravel", "amex travel", "prepaid hotel", "prepaid hotels"],
    "chase travel": ["chase travel", "travel purchased through chase"],
    "travel": ["travel purchases", "travel purchase", "other travel"],
    "gas stations": ["gas", "gas station", "fuel", "u.s. gas stations", "ev charging"],
    "lyft": ["lyft", "rideshare", "ride with lyft"],
    "air travel (capital one)": ["flights booked", "capital one travel", "air travel"],
    "hotels (capital one)": ["hotels booked", "capital one travel", "vacation rentals"],
    "car rentals (capital one)": ["rental cars booked", "capital one travel", "car rentals"],
    "ridesharing": ["transit", "rideshare", "taxi", "parking", "tolls"],
    "tolls": ["transit", "tolls", "parking", "rideshare"],
    "transit": ["transit", "trains", "buses", "rideshare"],
    "drugstores": ["drugstore", "drugstores", "pharmacy"],
    "streaming services": ["streaming", "select streaming", "digital media"],
    "telecom": ["telecom", "wireless", "phone", "internet"],
    "home improvement": ["home improvement", "hardware", "lumber"],
    "wholesale clubs": ["wholesale", "costco", "sam's club"],
    "rent": ["rent", "housing", "mortgage"],
    "cash back": ["cash back", "cashback"],
    "all purchases": ["every purchase", "all purchases", "everything you buy"],
}


@dataclass
class EvidenceVerdict:
    verdict: str
    action: str
    evidence_scrape: list[str] = field(default_factory=list)
    evidence_reference: list[str] = field(default_factory=list)
    summary: str = ""


def _terms_for_category(category_name: str, description: str = "") -> list[str]:
    blob = f"{category_name} {description}".lower()
    terms: list[str] = []
    for key, keywords in CATEGORY_SEARCH_TERMS.items():
        if key in blob or any(k in blob for k in keywords):
            terms.extend(keywords)
    if "top eligible spend category" in blob:
        terms.extend(["top eligible spend category", "top eligible spend"])
    if "choice category" in blob:
        terms.extend(["choice category", "cash back in"])
    if not terms:
        words = re.findall(r"[a-z]{4,}", category_name.lower())
        terms.extend(words[:4])
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out[:8]


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - SNIPPET_RADIUS)
    right = min(len(text), end + SNIPPET_RADIUS)
    snippet = text[left:right].strip()
    if left > 0:
        snippet = "…" + snippet
    if right < len(text):
        snippet = snippet + "…"
    return re.sub(r"\s+", " ", snippet)


def _multiplier_variants(value: float) -> list[str]:
    variants: list[str] = []
    if abs(value - round(value)) < 0.01:
        variants.append(str(int(round(value))))
    variants.append(f"{value:g}")
    return list(dict.fromkeys(variants))


def _earn_clauses(page_text: str) -> list[str]:
    """Split issuer copy into roughly one earn-rate sentence per clause."""
    text = re.sub(r"\s+", " ", page_text)
    parts = re.split(
        r"(?<=[.!?])\s+(?=Earn\s|\d+(?:\.\d+)?\s*[xX])",
        text,
        flags=re.I,
    )
    if len(parts) <= 1:
        parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _extract_multiplier_from_match(match: re.Match[str]) -> float | None:
    for group in match.groups():
        if group is None:
            continue
        try:
            return float(group)
        except ValueError:
            continue
    return None


def _term_in_text(term: str, text: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}s?\b", text, re.I))


def _custom_cash_top_category_snippet(page_text: str, multiplier: float) -> list[str]:
    text = re.sub(r"\s+", " ", page_text)
    match = re.search(
        rf"{multiplier:g}\s*%\s*cash back on your top eligible spend category",
        text,
        re.I,
    )
    if not match:
        return []
    return [_snippet(text, match.start(), match.end())]


def _bilt_lyft_snippet(page_text: str, multiplier: float) -> list[str]:
    if "lyft" not in page_text.lower():
        return []
    text = re.sub(r"\s+", " ", page_text)
    for pattern in (
        rf"(?:up to\s+)?{multiplier:g}\s*[xX×]\s*(?:points|pts).{{0,80}}\blyft\b",
        rf"\blyft\b.{{0,80}}(?:up to\s+)?{multiplier:g}\s*[xX×]\s*(?:points|pts)",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return [_snippet(text, match.start(), match.end())]
    return []


def find_evidence_snippets(
    page_text: str,
    multiplier: float,
    category_terms: list[str],
    *,
    limit: int = 3,
) -> list[str]:
    if not page_text or not category_terms:
        return []

    if any(term in ("top eligible spend", "top eligible spend category") for term in category_terms):
        custom = _custom_cash_top_category_snippet(page_text, multiplier)
        if custom:
            return custom

    if any(term == "lyft" for term in category_terms):
        lyft = _bilt_lyft_snippet(page_text, multiplier)
        if lyft:
            return lyft

    if any("capital one travel" in term for term in category_terms):
        text = re.sub(r"\s+", " ", page_text)
        for pattern in (
            rf"{MULTIPLIER_PATTERN}\s*(?:miles|Miles).{{0,80}}capital one travel",
            rf"capital one travel.{{0,80}}{MULTIPLIER_PATTERN}\s*(?:miles|Miles)",
            rf"{MULTIPLIER_PATTERN}\s*(?:miles|Miles).{{0,40}}booked through capital one travel",
        ):
            for match in re.finditer(pattern, text, re.I):
                found_mult = _extract_multiplier_from_match(match)
                if found_mult is not None and abs(found_mult - multiplier) <= 0.01:
                    return [_snippet(text, match.start(), match.end())]
        term_blob = " ".join(category_terms).lower()
        if re.search(r"showcase-5x", page_text, re.I):
            if ("hotel" in term_blob and "hotel" in text.lower()) or (
                "rental" in term_blob and "rental" in text.lower()
            ):
                match = re.search(r"showcase-5x", page_text, re.I)
                if match:
                    return [
                        _snippet(
                            text,
                            match.start(),
                            min(len(text), match.end() + 80),
                        )
                    ]

    snippets: list[str] = []
    seen: set[str] = set()

    for clause in _earn_clauses(page_text):
        text = re.sub(r"\s+", " ", clause)
        for term in category_terms:
            if not _term_in_text(term, text):
                continue
            term_pat = rf"{re.escape(term)}s?"
            patterns = [
                rf"{MULTIPLIER_PATTERN}.{{0,100}}\b{term_pat}\b",
                rf"\b{term_pat}\b.{{0,60}}{MULTIPLIER_PATTERN}",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.I):
                    found_mult = _extract_multiplier_from_match(match)
                    if found_mult is None or abs(found_mult - multiplier) > 0.01:
                        continue
                    snippet = _snippet(text, match.start(), match.end())
                    key = snippet.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    snippets.append(snippet)
                    if len(snippets) >= limit:
                        return snippets

    if snippets or not page_text:
        return snippets

    text = re.sub(r"\s+", " ", page_text)
    for term in category_terms:
        if not _term_in_text(term, text):
            continue
        term_pat = rf"{re.escape(term)}s?"
        for pattern in (
            rf"{MULTIPLIER_PATTERN}.{{0,120}}\b{term_pat}\b",
            rf"\b{term_pat}\b.{{0,80}}{MULTIPLIER_PATTERN}",
        ):
            for match in re.finditer(pattern, text, re.I):
                found_mult = _extract_multiplier_from_match(match)
                if found_mult is None or abs(found_mult - multiplier) > 0.01:
                    continue
                snippet = _snippet(text, match.start(), match.end())
                key = snippet.lower()
                if key in seen:
                    continue
                seen.add(key)
                snippets.append(snippet)
                if len(snippets) >= limit:
                    return snippets
    return snippets


def _pick_verdict(
    scrape_mult: float | None,
    ref_mult: float | None,
    scrape_evidence: list[str],
    ref_evidence: list[str],
    *,
    mismatch_type: str,
) -> EvidenceVerdict:
    has_scrape = bool(scrape_evidence)
    has_ref = bool(ref_evidence)

    if mismatch_type == "missing_in_reference":
        if has_scrape and not has_ref:
            return EvidenceVerdict(
                verdict="scrape_supported",
                action="keep_scrape",
                evidence_scrape=scrape_evidence,
                evidence_reference=ref_evidence,
                summary="Issuer page mentions this earn rate; API reference may be incomplete.",
            )
        if not has_scrape:
            return EvidenceVerdict(
                verdict="scrape_noise",
                action="fix_scrape",
                evidence_scrape=scrape_evidence,
                evidence_reference=ref_evidence,
                summary="No matching text on issuer page — likely parser noise.",
            )

    if mismatch_type == "missing_in_scrape":
        if has_ref and not has_scrape:
            return EvidenceVerdict(
                verdict="reference_supported",
                action="fix_scrape",
                evidence_scrape=scrape_evidence,
                evidence_reference=ref_evidence,
                summary="Issuer page supports API rate; scraper missed this category.",
            )
        if has_scrape and not has_ref:
            return EvidenceVerdict(
                verdict="scrape_supported",
                action="keep_scrape",
                evidence_scrape=scrape_evidence,
                evidence_reference=ref_evidence,
                summary="Issuer page text aligns with scraped interpretation.",
            )

    if has_scrape and not has_ref:
        return EvidenceVerdict(
            verdict="scrape_supported",
            action="keep_scrape",
            evidence_scrape=scrape_evidence,
            evidence_reference=ref_evidence,
            summary=(
                f"Website evidence supports scraped {scrape_mult}x; "
                f"no clear support for reference {ref_mult}x."
            ),
        )
    if has_ref and not has_scrape:
        return EvidenceVerdict(
            verdict="reference_supported",
            action="fix_scrape",
            evidence_scrape=scrape_evidence,
            evidence_reference=ref_evidence,
            summary=(
                f"Website evidence supports reference {ref_mult}x; "
                f"update scraper to match issuer page."
            ),
        )
    if has_scrape and has_ref:
        return EvidenceVerdict(
            verdict="both_supported",
            action="review_both",
            evidence_scrape=scrape_evidence,
            evidence_reference=ref_evidence,
            summary="Issuer page mentions both rates — wording may be ambiguous or conditional.",
        )
    return EvidenceVerdict(
        verdict="unclear",
        action="review_both",
        evidence_scrape=scrape_evidence,
        evidence_reference=ref_evidence,
        summary="No clear issuer-page snippet for either side — manual review.",
    )


def analyze_mismatch(
    *,
    mismatch_type: str,
    category_name: str,
    scrape_multiplier: float | None = None,
    reference_multiplier: float | None = None,
    scrape_description: str = "",
    reference_description: str = "",
    page_text: str,
) -> EvidenceVerdict:
    scrape_terms = _terms_for_category(category_name, scrape_description)
    ref_terms = _terms_for_category(category_name, reference_description or scrape_description)

    scrape_evidence: list[str] = []
    ref_evidence: list[str] = []

    if scrape_multiplier is not None:
        scrape_evidence = find_evidence_snippets(page_text, scrape_multiplier, scrape_terms)
    if reference_multiplier is not None:
        ref_evidence = find_evidence_snippets(page_text, reference_multiplier, ref_terms)

    return _pick_verdict(
        scrape_multiplier,
        reference_multiplier,
        scrape_evidence,
        ref_evidence,
        mismatch_type=mismatch_type,
    )


def analyze_base_rate_evidence(
    page_text: str,
    scrape_base: float,
    reference_base: float,
) -> EvidenceVerdict:
    scrape_evidence = find_evidence_snippets(
        page_text, scrape_base, ["every purchase", "all purchases", "cash back", "everything"]
    )
    ref_evidence = find_evidence_snippets(
        page_text, reference_base, ["every purchase", "all purchases", "cash back", "everything"]
    )
    return _pick_verdict(
        scrape_base,
        reference_base,
        scrape_evidence,
        ref_evidence,
        mismatch_type="base_rate_mismatch",
    )
