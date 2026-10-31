"""Core data models shared by every layer."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class Source(BaseModel):
    """One website to watch (an entry in config/sources.yaml)."""

    id: str
    name: str
    url: str
    state: str | None = None  # e.g. "Punjab"; None for national sites
    tier: int = 2  # 1 = every ~15 min, 2 = hourly, 3 = every ~6 h
    enabled: bool = True
    fetch_mode: str = "auto"  # auto | http | browser
    verify_ssl: bool = True  # some .gov.in sites have broken certificates
    note: str | None = None


class Candidate(BaseModel):
    """Something on a page that *might* be a notice: a link, table row or list item."""

    title: str
    url: str
    context: str = ""  # surrounding text (table row / list item)
    source_id: str = ""

    @property
    def fingerprint(self) -> str:
        basis = f"{self.url}|{normalize_text(self.title).lower()}"
        return hashlib.sha256(basis.encode()).hexdigest()[:32]

    @property
    def is_pdf(self) -> bool:
        return self.url.lower().split("?")[0].endswith(".pdf")

    @property
    def text(self) -> str:
        return normalize_text(f"{self.title} {self.context}")


class Classification(BaseModel):
    """Result of deciding whether a candidate is a rice auction notice."""

    is_rice_auction: bool
    confidence: float = 0.0
    method: str = "keyword"  # keyword | llm
    title: str = ""
    state: str | None = None
    location: str | None = None
    auction_date: str | None = None
    quantity: str | None = None
    reserve_price: str | None = None
    registration_deadline: str | None = None
    summary: str = ""


class Alert(BaseModel):
    """A rice-auction notice we intend to tell the user about."""

    key: str
    title: str
    urls: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    state: str | None = None
    location: str | None = None
    auction_date: str | None = None
    quantity: str | None = None
    reserve_price: str | None = None
    registration_deadline: str | None = None
    summary: str = ""
    confidence: float = 0.0
    method: str = "keyword"
    created_at: datetime = Field(default_factory=utcnow)
    notified: bool = False


class SourceState(BaseModel):
    """Per-source bookkeeping used for baselining and health monitoring."""

    source_id: str
    baselined: bool = False
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_change: datetime | None = None
    last_item_count: int = 0
    consecutive_failures: int = 0
    last_error: str | None = None
    health_alerted: bool = False


class Message(BaseModel):
    """A notification, rendered for both plain-text and HTML channels."""

    subject: str
    text: str
    html: str  # limited HTML (b, i, a) that Telegram and email both accept
