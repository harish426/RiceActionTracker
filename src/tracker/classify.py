"""Decide whether a candidate is a rice auction notice, and pull out the details.

Stage 1 (free, instant): keyword prefilter - drops the vast majority of links.
Stage 2: LLM (Claude) for accurate yes/no + structured fields, with a
keyword/regex fallback when no API key is configured or the call fails.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Protocol

from tracker.models import Alert, Candidate, Classification, normalize_text

log = logging.getLogger(__name__)

AUCTION_TERMS = [
    "auction", "e-auction", "eauction", "omss", "open market sale", "open market sales",
    "e-tender sale", "disposal of", "नीलामी", "ई-नीलामी", "खुला बाजार", "ఈ-వేలం", "వేలం",
    "ஏலம்", "ലേലം", "ಹರಾಜು", "নিলাম", "લિલામ",
]
RICE_TERMS = [
    "rice", "paddy", "frk", "cmr", "custom milled", "foodgrain", "food grain", "food-grain",
    "चावल", "धान", "అన్నం", "బియ్యం", "அரிசி", "അരി", "ಅಕ್ಕಿ", "চাল", "ચોખા",
]


def _has_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


def is_auction_like(text: str) -> bool:
    """Cheap prefilter: does this look like an auction/sale notice at all?"""
    return _has_any(text, AUCTION_TERMS)


def mentions_rice(text: str) -> bool:
    return _has_any(text, RICE_TERMS)


_DATE_RE = re.compile(
    r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})\b", re.IGNORECASE)
_QTY_RE = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s*(MT|M\.T\.?|metric\s+tonnes?|tonnes?|quintals?|LMT)\b", re.IGNORECASE)


class Classifier(Protocol):
    def classify(self, candidate: Candidate, extra_text: str = "") -> Classification: ...


class KeywordClassifier:
    """Fallback classifier: requires both an auction term and a rice term."""

    def classify(self, candidate: Candidate, extra_text: str = "") -> Classification:
        text = normalize_text(f"{candidate.text} {extra_text}")
        auction, rice = is_auction_like(text), mentions_rice(text)
        if not (auction and rice):
            return Classification(is_rice_auction=False, confidence=0.7, method="keyword",
                                  title=candidate.title)
        date = _DATE_RE.search(text)
        qty = _QTY_RE.search(text)
        return Classification(
            is_rice_auction=True, confidence=0.55, method="keyword", title=candidate.title,
            auction_date=date.group(1) if date else None,
            quantity=f"{qty.group(1)} {qty.group(2)}" if qty else None,
            summary=(candidate.context if candidate.context != candidate.title else "")[:300],
        )


_TOOL: dict[str, Any] = {
    "name": "report_notice",
    "description": "Report whether this web page item is a notice of a rice auction / sale by "
                   "the Government of India or a state agency (FCI OMSS, e-auction, state "
                   "civil supplies sale of rice/paddy/CMR/FRK).",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_rice_auction": {"type": "boolean",
                                "description": "True only for an actual new auction/sale notice "
                                "that includes rice (or foodgrains incl. rice). False for results, "
                                "tenders to BUY rice, procurement, wheat-only sales, circulars, "
                                "news, or navigation links."},
            "confidence": {"type": "number", "description": "0.0 - 1.0"},
            "title": {"type": "string"},
            "state": {"type": ["string", "null"]},
            "location": {"type": ["string", "null"], "description": "depot / district / region"},
            "auction_date": {"type": ["string", "null"], "description": "ISO yyyy-mm-dd if known"},
            "quantity": {"type": ["string", "null"]},
            "reserve_price": {"type": ["string", "null"]},
            "registration_deadline": {"type": ["string", "null"]},
            "summary": {"type": "string", "description": "one or two sentences in English"},
        },
        "required": ["is_rice_auction", "confidence", "summary"],
    },
}


class LLMClassifier:
    """Claude-based classifier using forced tool-use for validated structured output."""

    def __init__(self, client: Any, model: str, fallback: Classifier | None = None):
        self.client = client
        self.model = model
        self.fallback = fallback or KeywordClassifier()

    def classify(self, candidate: Candidate, extra_text: str = "") -> Classification:
        body = normalize_text(f"{candidate.text}\n{extra_text}")[:6000]
        prompt = (
            f"Page item found on an Indian government website.\nLink title: {candidate.title}\n"
            f"URL: {candidate.url}\nContent:\n{body}\n\n"
            "Decide if this is a notice of a rice auction/sale and extract the details. "
            "Text may be in Hindi or another Indian language."
        )
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=600, tools=[_TOOL],
                tool_choice={"type": "tool", "name": "report_notice"},
                messages=[{"role": "user", "content": prompt}],
            )
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    data = dict(block.input)
                    data.setdefault("title", candidate.title)
                    return Classification(method="llm", **{
                        k: v for k, v in data.items() if k in Classification.model_fields})
        except Exception:
            log.warning("LLM classification failed; using keyword fallback", exc_info=True)
        return self.fallback.classify(candidate, extra_text)


def build_classifier(api_key: str | None, model: str) -> Classifier:
    if not api_key:
        return KeywordClassifier()
    import anthropic

    return LLMClassifier(anthropic.Anthropic(api_key=api_key), model)


def alert_key(c: Classification, candidate: Candidate) -> str:
    """Same auction announced on two sites should map to the same key."""
    if c.state and c.auction_date:
        basis = f"{c.state.lower().strip()}|{c.auction_date.strip()}|{(c.quantity or '').lower()}"
    else:
        basis = candidate.fingerprint
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


def to_alert(c: Classification, candidate: Candidate, source_name: str, source_state: str | None) -> Alert:
    return Alert(
        key=alert_key(c, candidate), title=c.title or candidate.title, urls=[candidate.url],
        source_names=[source_name], state=c.state or source_state, location=c.location,
        auction_date=c.auction_date, quantity=c.quantity, reserve_price=c.reserve_price,
        registration_deadline=c.registration_deadline, summary=c.summary,
        confidence=c.confidence, method=c.method,
    )
