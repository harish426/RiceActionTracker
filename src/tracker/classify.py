"""Decide whether a candidate is a notice about a tracked commodity (rice / maize).

Stage 1 (free, instant): keyword prefilter - drops the vast majority of links.
Stage 2: LLM (Claude) for accurate yes/no + structured fields, with a
keyword/regex fallback when no API key is configured or the call fails.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Protocol

from tracker.commodities import ALL_COMMODITIES, detect_commodity, is_action_like
from tracker.models import Alert, Candidate, Classification, normalize_text

log = logging.getLogger(__name__)

_DATE_RE = re.compile(
    r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})\b", re.I)
_QTY_RE = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s*(MT|M\.T\.?|metric\s+tonnes?|tonnes?|quintals?|LMT)\b", re.I)
_TYPES = [("auction", ("auction", "नीलामी", "వేలం", "omss")), ("tender", ("tender", "निविदा", "టెండర్")),
          ("sale", ("sale", "sell", "बिक्री", "disposal"))]


def guess_notice_type(text: str) -> str:
    low = text.lower()
    for name, words in _TYPES:
        if any(w in low for w in words):
            return name
    return "auction"


class Classifier(Protocol):
    def classify(self, candidate: Candidate, extra_text: str = "") -> Classification: ...


class KeywordClassifier:
    """Fallback classifier: needs an action word (auction/sale/tender) AND a tracked commodity."""

    def __init__(self, commodities: list[str] | None = None):
        self.commodities = commodities or ["rice", "maize"]

    def classify(self, candidate: Candidate, extra_text: str = "") -> Classification:
        text = normalize_text(f"{candidate.text} {extra_text}")
        commodity = detect_commodity(text, self.commodities)
        if not (commodity and is_action_like(text)):
            return Classification(is_relevant=False, confidence=0.7, method="keyword",
                                  title=candidate.title)
        date = _DATE_RE.search(text)
        qty = _QTY_RE.search(text)
        return Classification(
            is_relevant=True, commodity=commodity, notice_type=guess_notice_type(text),
            confidence=0.55, method="keyword", title=candidate.title,
            auction_date=date.group(1) if date else None,
            quantity=f"{qty.group(1)} {qty.group(2)}" if qty else None,
            summary=(candidate.context if candidate.context != candidate.title else "")[:300],
        )


def _tool(commodities: list[str]) -> dict[str, Any]:
    names = ", ".join(ALL_COMMODITIES[c].label for c in commodities if c in ALL_COMMODITIES)
    return {
        "name": "report_notice",
        "description": f"Report whether this web page item is a notice that lets a BUYER obtain "
                       f"one of these commodities: {names} - i.e. an auction, e-auction, open "
                       "market sale, sale/disposal tender or bidding invitation by a government "
                       "body, cooperative or market committee in India.",
        "input_schema": {
            "type": "object",
            "properties": {
                "is_relevant": {"type": "boolean", "description":
                    "True only for an actual NEW auction/sale/tender-to-sell notice that "
                    "includes a tracked commodity. False for: results, procurement FROM farmers, "
                    "tenders to BUY/supply goods to government, wheat/pulse-only sales, "
                    "recruitment, circulars, news, navigation links."},
                "commodity": {"type": "string", "enum": [*commodities, "other"]},
                "notice_type": {"type": "string", "enum": ["auction", "sale", "tender", "market"]},
                "confidence": {"type": "number", "description": "0.0 - 1.0"},
                "title": {"type": "string"},
                "state": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"], "description": "depot / market yard / district"},
                "auction_date": {"type": ["string", "null"], "description": "ISO yyyy-mm-dd if known"},
                "quantity": {"type": ["string", "null"]},
                "reserve_price": {"type": ["string", "null"]},
                "registration_deadline": {"type": ["string", "null"]},
                "summary": {"type": "string", "description": "one or two sentences in English"},
            },
            "required": ["is_relevant", "commodity", "confidence", "summary"],
        },
    }


class LLMClassifier:
    """Claude-based classifier using forced tool-use for validated structured output."""

    def __init__(self, client: Any, model: str, commodities: list[str] | None = None,
                 fallback: Classifier | None = None):
        self.client = client
        self.model = model
        self.commodities = commodities or ["rice", "maize"]
        self.fallback = fallback or KeywordClassifier(self.commodities)

    def classify(self, candidate: Candidate, extra_text: str = "") -> Classification:
        body = normalize_text(f"{candidate.text}\n{extra_text}")[:6000]
        prompt = (
            f"Page item found on an Indian government / cooperative / market website.\n"
            f"Link title: {candidate.title}\nURL: {candidate.url}\nContent:\n{body}\n\n"
            "Decide if this is a notice relevant to a buyer of the tracked commodities and "
            "extract the details. Text may be in Hindi, Telugu or another Indian language."
        )
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=600, tools=[_tool(self.commodities)],
                tool_choice={"type": "tool", "name": "report_notice"},
                messages=[{"role": "user", "content": prompt}],
            )
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    data = dict(block.input)
                    data.setdefault("title", candidate.title)
                    result = Classification(method="llm", **{
                        k: v for k, v in data.items() if k in Classification.model_fields})
                    if result.is_relevant and result.commodity not in self.commodities:
                        result.is_relevant = False  # e.g. wheat / "other"
                    return result
        except Exception:
            log.warning("LLM classification failed; using keyword fallback", exc_info=True)
        return self.fallback.classify(candidate, extra_text)


def build_classifier(api_key: str | None, model: str,
                     commodities: list[str] | None = None) -> Classifier:
    if not api_key:
        return KeywordClassifier(commodities)
    import anthropic

    return LLMClassifier(anthropic.Anthropic(api_key=api_key), model, commodities)


def alert_key(c: Classification, candidate: Candidate) -> str:
    """Same auction announced on two sites should map to the same key."""
    if c.state and c.auction_date:
        basis = (f"{c.commodity}|{c.state.lower().strip()}|{c.auction_date.strip()}|"
                 f"{(c.quantity or '').lower()}")
    else:
        basis = f"{c.commodity}|{candidate.fingerprint}"
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


def to_alert(c: Classification, candidate: Candidate, source_name: str,
             source_state: str | None) -> Alert:
    return Alert(
        key=alert_key(c, candidate), title=c.title or candidate.title, commodity=c.commodity,
        notice_type=c.notice_type, urls=[candidate.url], source_names=[source_name],
        state=c.state or source_state, location=c.location, auction_date=c.auction_date,
        quantity=c.quantity, reserve_price=c.reserve_price,
        registration_deadline=c.registration_deadline, summary=c.summary,
        confidence=c.confidence, method=c.method,
    )
