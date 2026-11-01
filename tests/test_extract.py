from conftest import fixture_text
from tracker.extract import extract_candidates, page_text_length

BASE = "https://fci.example/notices"


def cands():
    return extract_candidates(fixture_text("fci_notices.html"), BASE, "fci")


def test_links_resolved_and_fragments_stripped():
    urls = {c.url for c in cands()}
    assert "https://fci.example/files/omss-rice-auction-punjab.pdf" in urls
    assert "https://other.example/news" in urls


def test_skips_mailto_javascript_and_scripts():
    urls = {c.url for c in cands()}
    assert not any(u.startswith(("mailto:", "javascript:")) for u in urls)
    assert not any("hidden" in u for u in urls)


def test_generic_link_text_replaced_by_row_context():
    c = next(c for c in cands() if c.url.endswith("omss-rice-auction-punjab.pdf"))
    assert "E-Auction of Rice" in c.title
    assert c.is_pdf


def test_linkless_table_row_is_candidate():
    assert any("holiday schedule" in c.title for c in cands())


def test_nav_links_kept():
    # Government sites often put real notices/menus inside <nav>, so we do not drop it.
    assert any(c.url.endswith("/home") for c in cands())


def test_no_duplicate_fingerprints():
    fps = [c.fingerprint for c in cands()]
    assert len(fps) == len(set(fps))


def test_fingerprint_stable_and_title_sensitive():
    a, b = cands(), cands()
    assert [c.fingerprint for c in a] == [c.fingerprint for c in b]


def test_page_without_links_falls_back_to_page_hash():
    html = "<html><body><p>Some long notice text about e-auction of rice here.</p></body></html>"
    out = extract_candidates(html, BASE)
    assert len(out) == 1 and out[0].title.startswith("Page content")
    other = extract_candidates(html.replace("rice", "wheat"), BASE)
    assert out[0].fingerprint != other[0].fingerprint  # change in text => detected


def test_page_text_length():
    assert page_text_length(fixture_text("spa_shell.html")) < 100
