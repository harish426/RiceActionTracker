from types import SimpleNamespace

from tracker.classify import (
    KeywordClassifier,
    LLMClassifier,
    alert_key,
    build_classifier,
    to_alert,
)
from tracker.commodities import commodity_hits, detect_commodity, is_action_like
from tracker.models import Candidate

C = Candidate(title="E-Auction of Rice under OMSS(D)", url="https://x/a.pdf",
              context="Auction on 12/11/2026 for 5,000 MT at Punjab depots")


def test_prefilter_english_and_hindi():
    assert is_action_like("OMSS sale of foodgrains")
    assert is_action_like("चावल की ई-नीलामी")
    assert not is_action_like("Recruitment of watchmen")
    assert commodity_hits("चावल", ["rice"])
    assert not commodity_hits("wheat only", ["rice", "maize"])


def test_keyword_classifier_positive_extracts_fields():
    r = KeywordClassifier().classify(C)
    assert r.is_relevant and r.method == "keyword" and r.commodity == "rice"
    assert r.auction_date == "12/11/2026"
    assert r.quantity.startswith("5,000")


def test_keyword_classifier_rejects_wheat_and_unrelated():
    k = KeywordClassifier()
    assert not k.classify(Candidate(title="OMSS wheat auction", url="u")).is_relevant
    assert not k.classify(Candidate(title="Rice procurement circular", url="u")).is_relevant


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
    payload = {"is_relevant": True, "commodity": "rice", "confidence": 0.93, "summary": "OMSS rice sale",
               "state": "Punjab", "auction_date": "2026-11-12", "quantity": "5000 MT",
               "ignored_extra_field": 1}
    client = FakeClient(payload)
    r = LLMClassifier(client, "m").classify(C)
    assert r.is_relevant and r.method == "llm" and r.state == "Punjab"
    assert client.calls[0]["tool_choice"]["name"] == "report_notice"


def test_llm_failure_falls_back_to_keywords():
    r = LLMClassifier(FakeClient(boom=True), "m").classify(C)
    assert r.is_relevant and r.method == "keyword"


def test_build_classifier_without_key_is_keyword():
    assert isinstance(build_classifier(None, "m"), KeywordClassifier)


def test_alert_key_same_auction_two_sites_matches():
    from tracker.models import Classification

    c = Classification(is_relevant=True, state="Punjab", auction_date="2026-11-12", quantity="5000 MT")
    a = alert_key(c, Candidate(title="a", url="https://site1/x"))
    b = alert_key(c, Candidate(title="b", url="https://site2/y"))
    assert a == b


def test_alert_key_without_state_date_is_per_candidate():
    from tracker.models import Classification

    c = Classification(is_relevant=True)
    assert alert_key(c, Candidate(title="a", url="u1")) != alert_key(c, Candidate(title="a", url="u2"))


def test_to_alert_uses_source_state_fallback():
    alert = to_alert(KeywordClassifier().classify(C), C, "FCI", "Punjab")
    assert alert.state == "Punjab" and alert.urls == [C.url] and alert.source_names == ["FCI"]


def test_word_boundaries_price_is_not_rice():
    assert not commodity_hits("Reserve price for wheat auction", ["rice"])
    assert not commodity_hits("cornice repair tender", ["maize"])
    assert KeywordClassifier().classify(
        Candidate(title="OMSS wheat e-auction reserve price 2,500", url="u")).is_relevant is False


def test_maize_detection_english_hindi_telugu():
    for text in ["Maize e-auction by MARKFED", "Corn sale tender", "मक्का की नीलामी",
                 "మొక్కజొన్న వేలం"]:
        assert detect_commodity(text, ["rice", "maize"]) == "maize", text
        assert is_action_like(text), text


def test_keyword_classifier_maize_and_commodity_filter():
    c = Candidate(title="Telangana MARKFED e-auction of maize 2,000 MT", url="u")
    r = KeywordClassifier().classify(c)
    assert r.is_relevant and r.commodity == "maize" and r.notice_type == "auction"
    assert not KeywordClassifier(["rice"]).classify(c).is_relevant  # maize not enabled


def test_tender_and_sale_notice_types():
    k = KeywordClassifier()
    assert k.classify(Candidate(title="Tender for sale of maize stock", url="u")).notice_type == "tender"
    assert k.classify(Candidate(title="Maize stock for sale", url="u")).notice_type == "sale"


def test_picks_dominant_commodity():
    assert detect_commodity("rice rice paddy and a little maize", ["rice", "maize"]) == "rice"


def test_llm_wheat_or_other_commodity_is_rejected():
    payload = {"is_relevant": True, "commodity": "other", "confidence": 0.9, "summary": "wheat"}
    assert not LLMClassifier(FakeClient(payload), "m").classify(C).is_relevant


def test_same_state_date_different_commodity_not_merged():
    from tracker.models import Classification

    a = Classification(is_relevant=True, commodity="rice", state="Telangana",
                       auction_date="2026-11-12", quantity="500 MT")
    b = a.model_copy(update={"commodity": "maize"})
    cand = Candidate(title="t", url="u")
    assert alert_key(a, cand) != alert_key(b, cand)
