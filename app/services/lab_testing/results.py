"""Importing results from a lab partner, with provenance and revision history.

- A result is matched to an order only when the lab, the order id and the patient all agree.
  A mismatch is refused, never guessed: one patient's result must never land in another's record.
- Every version the lab sends is kept. A corrected or amended result adds a new revision; the
  earlier one stays, with its own timestamps, so nothing is silently overwritten.
- Values, units and ranges are stored exactly as the lab sent them.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

PRELIMINARY = "preliminary"
FINAL = "final"
CORRECTED = "corrected"  # the lab amended a final result
STATUSES = {PRELIMINARY, FINAL, CORRECTED}


class ResultError(Exception):
    pass


@dataclass(frozen=True)
class LabMessage:
    """One result message from a lab (from HL7 v2, FHIR or a partner API, after parsing)."""

    partner_id: str
    order_id: str
    patient_ref: str  # the lab's patient reference for this order
    test_code: str
    value: str
    unit: str
    reference_range: str
    status: str
    collected_at: str
    reported_at: str
    source_message_id: str


@dataclass
class ResultRecord:
    order_id: str
    patient_id: str
    test_code: str
    revisions: list[dict] = field(default_factory=list)

    @property
    def current(self) -> dict:
        return self.revisions[-1]


@dataclass(frozen=True)
class OrderLink:
    order_id: str
    partner_id: str
    patient_id: str
    partner_patient_ref: str


class ResultStore:
    def __init__(self, links: list[OrderLink]) -> None:
        self.links = {link.order_id: link for link in links}
        self.records: dict[tuple[str, str], ResultRecord] = {}
        self.audit: list[dict] = []

    def ingest(self, message: LabMessage) -> ResultRecord:
        link = self.links.get(message.order_id)
        if link is None:
            raise ResultError("No order matches this result.")
        if link.partner_id != message.partner_id:
            raise ResultError("This result came from a lab the order was not sent to.")
        if link.partner_patient_ref != message.patient_ref:
            raise ResultError("The patient on this result does not match the order. It was not imported.")
        if message.status not in STATUSES:
            raise ResultError(f"Unknown result status: {message.status}")
        key = (message.order_id, message.test_code)
        record = self.records.get(key)
        if record is None:
            record = ResultRecord(order_id=message.order_id, patient_id=link.patient_id, test_code=message.test_code)
            self.records[key] = record
        elif any(rev["source_message_id"] == message.source_message_id for rev in record.revisions):
            return record  # the same message delivered twice
        elif record.current["status"] in (FINAL, CORRECTED) and message.status == PRELIMINARY:
            raise ResultError("A preliminary result can't replace a final one.")
        record.revisions.append({
            "value": message.value, "unit": message.unit, "reference_range": message.reference_range,
            "status": message.status, "collected_at": message.collected_at, "reported_at": message.reported_at,
            "source_message_id": message.source_message_id, "partner_id": message.partner_id,
            "received_at": datetime.now(UTC).isoformat(),
        })
        self.audit.append({"event": "result_received", "order_id": message.order_id, "test_code": message.test_code, "status": message.status, "revision": len(record.revisions)})
        return record

    def for_patient(self, patient_id: str) -> list[ResultRecord]:
        return [record for record in self.records.values() if record.patient_id == patient_id]
