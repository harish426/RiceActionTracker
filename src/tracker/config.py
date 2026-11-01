"""Settings (from environment / .env) and source list loading."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from tracker.models import Source


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- storage -------------------------------------------------------
    storage_backend: str = "sqlite"  # sqlite | firestore
    sqlite_path: str = "data/tracker.db"
    snapshot_backend: str = "local"  # local | gcs | none
    snapshot_dir: str = "data/snapshots"
    gcs_bucket: str | None = None
    google_cloud_project: str | None = None
    firestore_database: str = "(default)"

    # --- sources / fetching -------------------------------------------
    sources_file: str = "config/sources.yaml"
    user_agent: str = (
        "Mozilla/5.0 (compatible; RiceAuctionTracker/0.1; personal notice monitor)"
    )
    request_timeout: float = 30.0
    max_workers: int = 4
    host_min_interval: float = 2.0  # seconds between requests to the same host
    browser_enabled: bool = False  # needs: pip install '.[browser]' && playwright install chromium
    pdf_lookup_limit: int = 5  # max PDFs opened per source per run to classify vague links

    commodities: str = "rice,maize"  # comma-separated; known: rice, maize

    # --- LLM -----------------------------------------------------------
    anthropic_api_key: str | None = None
    llm_model: str = "claude-haiku-5-5"

    # --- Telegram ------------------------------------------------------
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # --- Email ---------------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_ssl: bool = False  # True = implicit TLS (port 465); False = STARTTLS
    email_from: str | None = None
    email_to: str | None = None  # comma-separated

    # --- health --------------------------------------------------------
    failure_alert_threshold: int = 3

    @property
    def commodity_keys(self) -> list[str]:
        return [c.strip().lower() for c in self.commodities.split(",") if c.strip()]

    @property
    def email_recipients(self) -> list[str]:
        return [e.strip() for e in (self.email_to or "").split(",") if e.strip()]


class SourcesFile(BaseModel):
    sources: list[Source]


def load_sources(path: str | Path) -> list[Source]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    parsed = SourcesFile.model_validate(data)
    ids = [s.id for s in parsed.sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate source ids in {path}: {sorted(dupes)}")
    return parsed.sources
