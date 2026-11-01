"""Turn any HTML page into a list of candidate notices.

No per-site selectors: every link becomes a candidate, with the text of its
nearest table row / list item as context. Table rows without links and (as a
last resort) the whole page are also covered, so *something* is always tracked.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urldefrag, urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from tracker.models import Candidate, normalize_text

_SKIP_SCHEMES = ("javascript:", "mailto:", "tel:", "#", "data:")
_CONTEXT_TAGS = {"tr", "li", "p"}
_MAX_CONTEXT = 500
_GENERIC_TITLES = {"click here", "view", "download", "more", "read more", "pdf", "here"}


def _context_for(node) -> str:
    parent = node.parent
    depth = 0
    while parent is not None and depth < 6:
        if parent.tag in _CONTEXT_TAGS:
            return normalize_text(parent.text(separator=" "))[:_MAX_CONTEXT]
        parent = parent.parent
        depth += 1
    return ""


def extract_candidates(html: str, base_url: str, source_id: str = "") -> list[Candidate]:
    tree = HTMLParser(html)
    for bad in tree.css("script, style, noscript"):
        bad.decompose()

    found: dict[str, Candidate] = {}

    def add(c: Candidate) -> None:
        found.setdefault(c.fingerprint, c)

    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.lower().startswith(_SKIP_SCHEMES):
            continue
        url, _ = urldefrag(urljoin(base_url, href))
        title = normalize_text(a.text(separator=" ")) or normalize_text(
            a.attributes.get("title") or ""
        )
        context = _context_for(a)
        if not title and not context:
            continue
        if title.lower() in _GENERIC_TITLES and context:
            title = context[:200]  # "Click here" is useless; the row text is the real title
        add(Candidate(title=title or context[:200], url=url, context=context, source_id=source_id))

    # Table rows that contain no link (plain-text notices)
    for tr in tree.css("tr"):
        if tr.css_first("a[href]"):
            continue
        text = normalize_text(tr.text(separator=" "))
        if len(text) >= 20:
            add(Candidate(title=text[:200], url=base_url, context=text[:_MAX_CONTEXT],
                          source_id=source_id))

    if not found:
        body = tree.body
        text = normalize_text(body.text(separator=" ") if body else "")
        if text:
            digest = hashlib.sha256(text.encode()).hexdigest()[:12]
            add(Candidate(title=f"Page content {digest}", url=base_url, context=text[:_MAX_CONTEXT],
                          source_id=source_id))
    return list(found.values())


def page_text_length(html: str) -> int:
    tree = HTMLParser(html)
    for bad in tree.css("script, style, noscript"):
        bad.decompose()
    body = tree.body
    return len(normalize_text(body.text(separator=" "))) if body else 0
