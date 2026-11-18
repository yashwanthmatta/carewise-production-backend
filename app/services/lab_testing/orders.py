"""The lab order state machine.

Rules it enforces (each has a test):
- Nothing moves without a passing eligibility decision.
- A clinician-order request cannot be paid for, submitted or booked until a licensed clinician
  records a decision. Paying never approves an order; the AI never approves one.
- Only the assigned clinician, with a credential and a licence state, can approve, decline or ask
  for more information, and only in a state they are licensed in.
- A booking counts only when the lab partner confirms it. A failed booking does not charge.
- The same request twice (same idempotency key) is one order.
- Cancelling after payment records a refund owed. Nothing is deleted; every step is in the audit trail.
- While lab testing is not live (LIVE is False), submit() refuses, whatever else is true.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.services.lab_testing import LIVE
from app.services.lab_testing.eligibility import CLINICIAN_ORDER, Decision
from app.services.lab_testing.partners import LabPartnerAdapter, Slot

DRAFT = "draft"
AWAITING_CLINICIAN = "awaiting_clinician"
NEEDS_INFO = "needs_info"
DECLINED = "declined"
APPROVED = "approved"
PAID = "paid"
SUBMITTED = "submitted"
BOOKED = "booked"
BOOKING_FAILED = "booking_failed"
COLLECTED = "collected"
RESULTED = "resulted"
CANCELLED = "cancelled"

ALLOWED = {
    DRAFT: {AWAITING_CLINICIAN, APPROVED, CANCELLED},
    AWAITING_CLINICIAN: {APPROVED, DECLINED, NEEDS_INFO, CANCELLED},
    NEEDS_INFO: {AWAITING_CLINICIAN, CANCELLED},
    APPROVED: {PAID, CANCELLED},
    PAID: {SUBMITTED, CANCELLED},
    SUBMITTED: {BOOKED, BOOKING_FAILED, CANCELLED},
    BOOKING_FAILED: {BOOKED, CANCELLED},
    BOOKED: {COLLECTED, CANCELLED},
    COLLECTED: {RESULTED},
    DECLINED: set(),
    RESULTED: set(),
    CANCELLED: set(),
}


class OrderError(Exception):
    pass


@dataclass(frozen=True)
class Clinician:
    id: str
    name: str
    credential: str  # e.g. MD, DO, NP, PA
    licence_states: tuple[str, ...]


@dataclass
class Order:
    id: str
    patient_id: str
    test_keys: tuple[str, ...]
    state: str
    pathway: str
    idempotency_key: str
    status: str = DRAFT
    assigned_clinician_id: str = ""
    clinician_decision: dict = field(default_factory=dict)
    payment_ref: str = ""
    refund_owed: bool = False
    booking: dict = field(default_factory=dict)
    audit: list[dict] = field(default_factory=list)

    def _move(self, to: str, actor: str, **detail) -> None:
        if to not in ALLOWED[self.status]:
            raise OrderError(f"An order can't go from {self.status} to {to}.")
        self.audit.append({"at": datetime.now(UTC).isoformat(), "from": self.status, "to": to, "actor": actor, **detail})
        self.status = to


class OrderBook:
    """Orders in memory, keyed by idempotency key. Persistence comes with the reviewed migration."""

    def __init__(self) -> None:
        self.by_key: dict[str, Order] = {}

    def create(self, *, order_id: str, patient_id: str, test_keys: list[str], state: str, decision: Decision, idempotency_key: str) -> Order:
        if idempotency_key in self.by_key:
            return self.by_key[idempotency_key]
        if not decision.allowed:
            raise OrderError("This test can't be ordered: " + " ".join(decision.reasons))
        order = Order(id=order_id, patient_id=patient_id, test_keys=tuple(test_keys), state=state.upper(), pathway=decision.pathway, idempotency_key=idempotency_key)
        order.audit.append({"at": datetime.now(UTC).isoformat(), "from": "", "to": DRAFT, "actor": f"patient:{patient_id}"})
        if decision.pathway == CLINICIAN_ORDER:
            order._move(AWAITING_CLINICIAN, "system", reason="needs a licensed clinician's decision")
        else:
            order._move(APPROVED, "system", reason="direct-access pathway allowed by a reviewed rule")
        self.by_key[idempotency_key] = order
        return order


def assign(order: Order, clinician: Clinician, actor: str) -> None:
    if order.status not in (AWAITING_CLINICIAN, NEEDS_INFO):
        raise OrderError("Only an order waiting for a clinician can be assigned.")
    order.assigned_clinician_id = clinician.id
    order.audit.append({"at": datetime.now(UTC).isoformat(), "event": "assigned", "clinician": clinician.id, "actor": actor})


def clinician_decides(order: Order, clinician: Clinician, decision: str, note: str = "") -> None:
    """A licensed clinician's own decision. decision is 'approve', 'decline' or 'needs_info'."""
    if order.pathway != CLINICIAN_ORDER:
        raise OrderError("This order does not use the clinician pathway.")
    if not order.assigned_clinician_id or clinician.id != order.assigned_clinician_id:
        raise OrderError("Only the clinician assigned to this order can decide on it.")
    if not clinician.credential or not clinician.licence_states:
        raise OrderError("A clinician needs a recorded credential and licence state to decide.")
    if order.state not in clinician.licence_states:
        raise OrderError(f"This clinician is not licensed in {order.state}.")
    target = {"approve": APPROVED, "decline": DECLINED, "needs_info": NEEDS_INFO}.get(decision)
    if not target:
        raise OrderError("Unknown decision.")
    if order.status == NEEDS_INFO and target != AWAITING_CLINICIAN:
        order._move(AWAITING_CLINICIAN, f"clinician:{clinician.id}", reason="information received")
    record = {"clinician_id": clinician.id, "name": clinician.name, "credential": clinician.credential, "licence_state": order.state, "decision": decision, "note": note, "at": datetime.now(UTC).isoformat()}
    order._move(target, f"clinician:{clinician.id}", **{"decision": decision})
    order.clinician_decision = record


def record_payment(order: Order, payment_ref: str) -> None:
    """Payment is only accepted once an order is approved. It never approves anything itself."""
    if order.status != APPROVED:
        raise OrderError("An order can only be paid for after it is approved.")
    if order.pathway == CLINICIAN_ORDER and order.clinician_decision.get("decision") != "approve":
        raise OrderError("A clinician has not approved this order.")
    order.payment_ref = payment_ref
    order._move(PAID, "payment", payment_ref=payment_ref)


def submit_and_book(order: Order, adapter: LabPartnerAdapter, slot: Slot, *, synthetic_run: bool = False) -> None:
    """Send the order to the lab and book the slot. Refused while lab testing is not live, unless it
    is an explicit synthetic run against a synthetic partner (tests and demos)."""
    if not LIVE and not (synthetic_run and adapter.partner.synthetic):
        raise OrderError("Lab testing is not live. No order can be sent to a lab.")
    if order.status not in (PAID, BOOKING_FAILED):
        raise OrderError("Only a paid order can be sent to the lab.")
    if order.status == PAID:
        order._move(SUBMITTED, "system", partner=adapter.partner.id)
    ack = adapter.book(slot, order.id)
    if ack.confirmed and ack.partner_booking_id:
        order.booking = {"partner_booking_id": ack.partner_booking_id, "slot_id": slot.partner_slot_id, "starts_at": slot.starts_at.isoformat()}
        order._move(BOOKED, f"partner:{adapter.partner.id}", partner_booking_id=ack.partner_booking_id)
    elif order.status != BOOKING_FAILED:
        order._move(BOOKING_FAILED, f"partner:{adapter.partner.id}", partner_status=ack.raw_status)


def cancel(order: Order, actor: str, adapter: LabPartnerAdapter | None = None) -> None:
    if order.status == BOOKED and adapter is not None:
        adapter.cancel(order.booking.get("partner_booking_id", ""))
    if order.payment_ref:
        order.refund_owed = True
    order._move(CANCELLED, actor, refund_owed=order.refund_owed)
