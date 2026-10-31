from types import SimpleNamespace

from tracker.classify import (
    KeywordClassifier,
    LLMClassifier,
    alert_key,
    build_classifier,
    is_auction_like,
    mentions_rice,
    to_alert,
)
from tracker.models import Candidate

C = Candidate(title="E-Auction of Rice under OMSS(D)", url="https://x/a.pdf",
              context="Auction on 12/11/2026 for 5,000 MT at Punjab depots")


def test_prefilter_english_and_hindi():
    assert is_auction_like("OMSS sale of foodgrains")
    assert is_auction_like("चावल की ई-नीलामी")
    assert not is_auction_like("Recruitment of watchmen")
    assert mentions_rice("चावल")
    assert not mentions_rice("wheat only")


def test_keyword_classifier_positive_extracts_fields():
    r = KeywordClassifier().classify(C)
    assert r.is_rice_auction and r.method == "keyword"
    assert r.auction_date == "12/11/2026"
    assert r.quantity.startswith("5,000")


def test_keyword_classifier_rejects_wheat_and_unrelated():
    k = KeywordClassifier()
    assert not k.classify(Candidate(title="OMSS wheat auction", url="u")).is_rice_auction
    assert not k.classify(Candidate(title="Rice procurement circular", url="u")).is_rice_auction


class FakeClient:
    def __init__(self, payload=None, boom=False):
        self.payload, self.boom = payload, boom
        self.messages = self
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise RuntimeError("api down")
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self.payload)])


def test_llm_classifier_parses_tool_output():
    payload = {"is_rice_auction": True, "confidence": 0.93, "summary": "OMSS rice sale",
               "state": "Punjab", "auction_date": "2026-11-12", "quantity": "5000 MT",
               "ignored_extra_field": 1}
    client = FakeClient(payload)
    r = LLMClassifier(client, "m").classify(C)
    assert r.is_rice_auction and r.method == "llm" and r.state == "Punjab"
    assert client.calls[0]["tool_choice"]["name"] == "report_notice"


def test_llm_failure_falls_back_to_keywords():
    r = LLMClassifier(FakeClient(boom=True), "m").classify(C)
    assert r.is_rice_auction and r.method == "keyword"


def test_build_classifier_without_key_is_keyword():
    assert isinstance(build_classifier(None, "m"), KeywordClassifier)


def test_alert_key_same_auction_two_sites_matches():
    from tracker.models import Classification

    c = Classification(is_rice_auction=True, state="Punjab", auction_date="2026-11-12", quantity="5000 MT")
    a = alert_key(c, Candidate(title="a", url="https://site1/x"))
    b = alert_key(c, Candidate(title="b", url="https://site2/y"))
    assert a == b


def test_alert_key_without_state_date_is_per_candidate():
    from tracker.models import Classification

    c = Classification(is_rice_auction=True)
    assert alert_key(c, Candidate(title="a", url="u1")) != alert_key(c, Candidate(title="a", url="u2"))


def test_to_alert_uses_source_state_fallback():
    alert = to_alert(KeywordClassifier().classify(C), C, "FCI", "Punjab")
    assert alert.state == "Punjab" and alert.urls == [C.url] and alert.source_names == ["FCI"]
