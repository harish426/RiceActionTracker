from __future__ import annotations

import io

from pypdf import PdfReader


def pdf_to_text(data: bytes, max_pages: int = 8) -> str:
    """Extract text from a text-based PDF. Scanned PDFs return '' (OCR is a later phase)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:max_pages]
        return "\n".join((p.extract_text() or "") for p in pages).strip()
    except Exception:
        return ""
