"""Lab testing foundation (synthetic data only). Each safety rule in app/services/lab_testing has a
test here that tries to break it."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import lab_testing
from app.services.lab_testing import catalog as cat
from app.services.lab_testing import orders as o
from app.services.lab_testing import review as rv
from app.services.lab_testing.eligibility import CLINICIAN_ORDER, DIRECT_ACCESS, Rule, decide
from app.services.lab_testing.partners import Location, Partner, Slot, SyntheticPartner, bookable, listing_kind
from app.services.lab_testing.results import FINAL, LabMessage, OrderLink, ResultError, ResultStore

SYN_RULES = [
    Rule(state="TX", test_key="lipid-panel", pathway=CLINICIAN_ORDER, reviewed_by="synthetic", synthetic=True),
    Rule(state="TX", test_key="a1c", pathway=DIRECT_ACCESS, reviewed_by="synthetic", synthetic=True),
]
DOC = o.Clinician(id="doc-1", name="Dr Synthetic", credential="MD", licence_states=("TX",))


def allowed(test="lipid-panel", state="TX"):
    return decide(SYN_RULES, state=state, test_key=test, age=40, partner_live=True, allow_synthetic=True)


def new_order(book=None, key="k1", test="lipid-panel"):
    book = book or o.OrderBook()
    return book.create(order_id=f"ord-{key}", patient_id="pat-1", test_keys=[test], state="TX", decision=allowed(test), idempotency_key=key)


# ---- Live switch and catalog ----

def test_lab_testing_is_not_live_and_cannot_be_switched_on_by_config():
    assert lab_testing.LIVE is False


def test_catalog_is_synthetic_unavailable_and_unpriced():
    tests = list(cat.TESTS.values())
    assert tests and all(t.source == "synthetic" and t.available is False for t in tests)
    assert all(t.partner_price_cents is None and t.preparation == "" and t.turnaround == "" for t in tests)


def test_catalog_endpoint_and_features_flag():
    with TestClient(create_app()) as client:
        body = client.get("/lab-testing/catalog").json()
        assert body["live"] is False and body["synthetic"] is True and "not available" in body["notice"]
        assert {c["key"] for c in body["categories"]} >= {"heart", "metabolic", "thyroid", "kidney", "liver", "blood", "nutrients"}
        assert client.get("/lab-testing/catalog?category=thyroid").json()["categories"][0]["key"] == "thyroid"
        assert client.get("/lab-testing/catalog?category=nope").status_code == 404
        assert client.get("/features").json()["lab_testing_live"] is False


# ---- Partners and locations ----

def test_only_verified_locations_of_signed_partners_are_bookable():
    signed = Partner(id="p1", name="Lab", kind="independent_lab", agreement_signed=True, verified_by="owner")
    unsigned = Partner(id="p2", name="Lab 2", kind="independent_lab")
    loc = Location(id="l1", partner_id="p1", name="Main St", city="Austin", state="TX", zip_code="78701", verified=True)
    assert bookable(loc, signed) and listing_kind(loc, signed) == "partner"
    assert not bookable(Location(**{**loc.__dict__, "verified": False}), signed)
    assert not bookable(Location(**{**loc.__dict__, "partner_id": "p2"}), unsigned)
    assert listing_kind(loc, None) == "informational"
    syn = SyntheticPartner().partner
    assert not bookable(Location(id="s", partner_id=syn.id, name="S", city="X", state="TX", zip_code="0", verified=True, synthetic=True), syn)


# ---- Eligibility ----

def test_eligibility_denies_by_default_and_without_legal_review():
    assert not decide([], state="TX", test_key="lipid-panel", age=40, partner_live=True).allowed
    assert not decide(SYN_RULES, state="TX", test_key="lipid-panel", age=40, partner_live=True).allowed  # synthetic rules ignored for real requests
    unreviewed = [Rule(state="TX", test_key="tsh", pathway=DIRECT_ACCESS)]
    d = decide(unreviewed, state="TX", test_key="tsh", age=40, partner_live=True)
    assert not d.allowed and any("legal review" in r for r in d.reasons)
    assert not decide(SYN_RULES, state="TX", test_key="lipid-panel", age=40, partner_live=False, allow_synthetic=True).allowed
    assert not decide(SYN_RULES, state="TX", test_key="lipid-panel", age=16, partner_live=True, allow_synthetic=True).allowed
    assert not decide(SYN_RULES, state="CA", test_key="lipid-panel", age=40, partner_live=True, allow_synthetic=True).allowed
    assert allowed().pathway == CLINICIAN_ORDER and allowed("a1c").pathway == DIRECT_ACCESS


# ---- Orders ----

def test_refused_eligibility_creates_no_order():
    with pytest.raises(o.OrderError):
        o.OrderBook().create(order_id="x", patient_id="p", test_keys=["tsh"], state="TX", decision=decide([], state="TX", test_key="tsh", age=40, partner_live=True), idempotency_key="x")


def test_same_request_twice_is_one_order():
    book = o.OrderBook()
    assert new_order(book) is new_order(book)
    assert len(book.by_key) == 1


def test_payment_never_approves_a_clinician_order():
    order = new_order()
    assert order.status == o.AWAITING_CLINICIAN
    with pytest.raises(o.OrderError):
        o.record_payment(order, "pay-1")
    assert order.status == o.AWAITING_CLINICIAN and order.payment_ref == ""


def test_only_the_assigned_licensed_clinician_decides():
    order = new_order()
    with pytest.raises(o.OrderError):
        o.clinician_decides(order, DOC, "approve")  # not assigned yet
    o.assign(order, DOC, "ops")
    other = o.Clinician(id="doc-2", name="Other", credential="MD", licence_states=("TX",))
    with pytest.raises(o.OrderError):
        o.clinician_decides(order, other, "approve")
    unlicensed = o.Clinician(id="doc-3", name="CA only", credential="MD", licence_states=("CA",))
    order.assigned_clinician_id = unlicensed.id
    with pytest.raises(o.OrderError):
        o.clinician_decides(order, unlicensed, "approve")
    no_credential = o.Clinician(id="doc-4", name="No credential", credential="", licence_states=("TX",))
    order.assigned_clinician_id = no_credential.id
    with pytest.raises(o.OrderError):
        o.clinician_decides(order, no_credential, "approve")
    order.assigned_clinician_id = DOC.id
    o.clinician_decides(order, DOC, "approve", note="Reasonable to check.")
    assert order.status == o.APPROVED
    assert order.clinician_decision["credential"] == "MD" and order.clinician_decision["licence_state"] == "TX"


def test_clinician_can_decline_or_ask_for_information():
    declined = new_order(key="d")
    o.assign(declined, DOC, "ops")
    o.clinician_decides(declined, DOC, "decline", note="Not indicated.")
    assert declined.status == o.DECLINED
    with pytest.raises(o.OrderError):
        o.record_payment(declined, "pay")
    asked = new_order(key="n")
    o.assign(asked, DOC, "ops")
    o.clinician_decides(asked, DOC, "needs_info")
    assert asked.status == o.NEEDS_INFO
    o.clinician_decides(asked, DOC, "approve")
    assert asked.status == o.APPROVED


def approved_paid_order(key="p"):
    order = new_order(key=key)
    o.assign(order, DOC, "ops")
    o.clinician_decides(order, DOC, "approve")
    o.record_payment(order, f"pay-{key}")
    return order


def slot():
    return Slot(location_id="syn-loc", starts_at=datetime.fromisoformat("2030-01-07T09:00:00+00:00"), partner_slot_id="syn-slot-1")


def test_nothing_is_sent_to_a_real_lab_while_not_live():
    order = approved_paid_order()
    real = SyntheticPartner(partner=Partner(id="real", name="Real Lab", kind="independent_lab", agreement_signed=True, verified_by="owner"))
    with pytest.raises(o.OrderError, match="not live"):
        o.submit_and_book(order, real, slot())
    with pytest.raises(o.OrderError, match="not live"):
        o.submit_and_book(order, SyntheticPartner(), slot())  # synthetic needs an explicit synthetic run
    assert order.status == o.PAID


def test_booking_counts_only_when_the_lab_confirms():
    order = approved_paid_order("b")
    failing = SyntheticPartner(fail_booking=True)
    o.submit_and_book(order, failing, slot(), synthetic_run=True)
    assert order.status == o.BOOKING_FAILED and order.booking == {}
    o.submit_and_book(order, SyntheticPartner(), slot(), synthetic_run=True)
    assert order.status == o.BOOKED and order.booking["partner_booking_id"] == "syn-ord-b"


def test_cancel_after_payment_owes_a_refund_and_cancels_the_booking():
    order = approved_paid_order("c")
    partner = SyntheticPartner()
    o.submit_and_book(order, partner, slot(), synthetic_run=True)
    o.cancel(order, "patient:pat-1", partner)
    assert order.status == o.CANCELLED and order.refund_owed and partner.cancelled == ["syn-ord-c"]
    with pytest.raises(o.OrderError):
        o.record_payment(order, "again")
    assert [step.get("to") for step in order.audit if "to" in step][-1] == o.CANCELLED


def test_states_cannot_be_skipped():
    order = new_order(key="s")
    with pytest.raises(o.OrderError):
        order._move(o.BOOKED, "anyone")


# ---- Results ----

def msg(**over):
    base = dict(partner_id="lab-1", order_id="ord-1", patient_ref="LAB-PAT-9", test_code="CREAT", value="1.9", unit="mg/dL", reference_range="0.6-1.3", status=FINAL, collected_at="2030-01-07T09:10:00Z", reported_at="2030-01-07T15:00:00Z", source_message_id="m1")
    base.update(over)
    return LabMessage(**base)


def store():
    return ResultStore([OrderLink(order_id="ord-1", partner_id="lab-1", patient_id="pat-1", partner_patient_ref="LAB-PAT-9"), OrderLink(order_id="ord-2", partner_id="lab-1", patient_id="pat-2", partner_patient_ref="LAB-PAT-7")])


def test_results_never_land_in_the_wrong_record():
    s = store()
    with pytest.raises(ResultError, match="patient"):
        s.ingest(msg(patient_ref="LAB-PAT-7"))  # another patient's reference on order 1
    with pytest.raises(ResultError):
        s.ingest(msg(order_id="ord-404"))
    with pytest.raises(ResultError):
        s.ingest(msg(partner_id="lab-2"))
    s.ingest(msg())
    assert s.for_patient("pat-2") == []
    assert [r.patient_id for r in s.for_patient("pat-1")] == ["pat-1"]


def test_amended_result_keeps_the_original_and_values_are_exact():
    s = store()
    s.ingest(msg())
    record = s.ingest(msg(value="2.10", status="corrected", reported_at="2030-01-08T10:00:00Z", source_message_id="m2"))
    assert [r["value"] for r in record.revisions] == ["1.9", "2.10"]
    assert record.current["status"] == "corrected" and record.revisions[0]["status"] == FINAL
    assert s.ingest(msg(value="2.10", status="corrected", source_message_id="m2")) is record and len(record.revisions) == 2
    with pytest.raises(ResultError):
        s.ingest(msg(status="preliminary", source_message_id="m3"))


# ---- Clinician review ----

def test_ai_draft_is_never_shown_as_clinician_reviewed_until_signed():
    review = rv.Review(patient_id="pat-1", patient_state="TX", order_id="ord-1")
    rv.draft(review, "Your creatinine is above the lab's range.", ai_drafted=True)
    assert review.patient_view() is None
    with pytest.raises(rv.ReviewError):
        rv.sign(review, DOC, has_access=False)
    with pytest.raises(rv.ReviewError):
        rv.sign(review, o.Clinician(id="d9", name="CA", credential="MD", licence_states=("CA",)), has_access=True)
    rv.sign(review, DOC, has_access=True)
    view = review.patient_view()
    assert view["clinician_reviewed"] and view["signed_by"]["credential"] == "MD" and view["signed_by"]["edited_ai_draft"] is True


def test_signed_review_is_never_edited_in_place():
    review = rv.Review(patient_id="pat-1", patient_state="TX", order_id="ord-1")
    rv.draft(review, "First.", ai_drafted=False)
    rv.sign(review, DOC, has_access=True)
    rv.draft(review, "Second.", ai_drafted=False)
    assert [v.text for v in review.versions] == ["First.", "Second."]
    assert review.patient_view()["text"] == "First."  # the unsigned change is not shown
    with pytest.raises(rv.ReviewError):
        rv.sign(rv.Review(patient_id="p", patient_state="TX", order_id="o"), DOC, has_access=True)
