"""Which commodities we track, and the words that identify them (English + Indian languages)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Commodity:
    key: str
    label: str  # shown in alerts
    emoji: str
    terms: tuple[str, ...]


RICE = Commodity("rice", "Rice", "🌾", (
    "rice", "paddy", "frk", "cmr", "custom milled", "foodgrain", "foodgrains", "food grain",
    "food grains", "food-grain", "चावल", "धान", "బియ్యం", "వరి", "அரிசி", "അരി", "ಅಕ್ಕಿ", "চাল", "ચોખા",
))
MAIZE = Commodity("maize", "Maize (Corn)", "🌽", (
    "maize", "corn", "makka", "makkai", "coarse grain", "coarse grains", "मक्का", "मक्की",
    "मक्कई", "మొక్కజొన్న", "மக்காச்சோளம்", "ಮೆಕ್ಕೆಜೋಳ",
))

ALL_COMMODITIES: dict[str, Commodity] = {c.key: c for c in (RICE, MAIZE)}

# Words that signal a chance to BUY: auction, sale, tender to sell, bidding.
ACTION_TERMS = (
    "auction", "e-auction", "eauction", "omss", "open market sale", "sale", "sales", "sell",
    "tender", "tenders", "bid", "bids", "bidding", "disposal", "नीलामी", "ई-नीलामी", "निविदा",
    "बिक्री", "వేలం", "ఈ-వేలం", "టెండర్", "ஏலம்", "ലേലം", "ಹರಾಜು", "নিলাম", "લિલામ",
)


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    """ASCII words match on word boundaries (so 'price' does not match 'rice'); others as-is."""
    parts = []
    for t in terms:
        esc = re.escape(t.lower())
        parts.append(rf"(?<![a-z0-9]){esc}(?![a-z0-9])" if t.isascii() else esc)
    return re.compile("|".join(parts))


_ACTION_RE = _compile(ACTION_TERMS)
_COMMODITY_RE = {k: _compile(c.terms) for k, c in ALL_COMMODITIES.items()}


def is_action_like(text: str) -> bool:
    """Cheap prefilter: does this look like an auction/sale/tender notice at all?"""
    return bool(_ACTION_RE.search(text.lower()))


def commodity_hits(text: str, keys: list[str]) -> dict[str, int]:
    low = text.lower()
    hits = {k: len(_COMMODITY_RE[k].findall(low)) for k in keys if k in _COMMODITY_RE}
    return {k: n for k, n in hits.items() if n}


def detect_commodity(text: str, keys: list[str]) -> str | None:
    """The tracked commodity mentioned most in the text (ties: first in `keys`)."""
    hits = commodity_hits(text, keys)
    return max(hits, key=lambda k: (hits[k], -keys.index(k))) if hits else None


def get_commodity(key: str | None) -> Commodity | None:
    return ALL_COMMODITIES.get(key or "")
