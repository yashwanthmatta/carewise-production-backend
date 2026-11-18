"""Clinician review of lab results.

- The AI may draft a summary. A draft is always marked as AI-drafted and is never shown to a
  patient as clinician-reviewed.
- Only a clinician with a recorded credential, licensed in the patient's state and with access to
  this patient, can sign. Signing records who, which credential, which state and when.
- A signed review is never edited in place. A change creates a new version that must be signed
  again; earlier versions stay in the history.
- A finding the clinician flags as urgent is not left to the app: it needs the separate
  critical-result process agreed with the lab and the clinical partner (see the architecture doc).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.services.lab_testing.orders import Clinician

DRAFT = "draft"
SIGNED = "signed"


class ReviewError(Exception):
    pass


@dataclass
class ReviewVersion:
    text: str
    ai_drafted: bool
    status: str = DRAFT
    signed_by: dict = field(default_factory=dict)
    urgent_flags: tuple[str, ...] = ()


@dataclass
class Review:
    patient_id: str
    patient_state: str
    order_id: str
    versions: list[ReviewVersion] = field(default_factory=list)

    @property
    def current(self) -> ReviewVersion:
        return self.versions[-1]

    def patient_view(self) -> dict | None:
        """What a patient may see as clinician-reviewed: only the latest signed version."""
        signed = [v for v in self.versions if v.status == SIGNED]
        if not signed:
            return None
        latest = signed[-1]
        return {"text": latest.text, "signed_by": latest.signed_by, "clinician_reviewed": True}


def draft(review: Review, text: str, *, ai_drafted: bool) -> None:
    if review.versions and review.current.status == DRAFT:
        review.current.text = text
        review.current.ai_drafted = review.current.ai_drafted or ai_drafted
        return
    review.versions.append(ReviewVersion(text=text, ai_drafted=ai_drafted))


def sign(review: Review, clinician: Clinician, *, has_access: bool, urgent_flags: tuple[str, ...] = ()) -> None:
    if not has_access:
        raise ReviewError("This clinician has no access to this patient's results.")
    if not clinician.credential or not clinician.licence_states:
        raise ReviewError("A clinician needs a recorded credential and licence state to sign.")
    if review.patient_state.upper() not in clinician.licence_states:
        raise ReviewError(f"This clinician is not licensed in {review.patient_state}.")
    if not review.versions or review.current.status != DRAFT:
        raise ReviewError("There is no draft to sign.")
    if not review.current.text.strip():
        raise ReviewError("An empty review can't be signed.")
    version = review.current
    version.status = SIGNED
    version.urgent_flags = tuple(urgent_flags)
    version.signed_by = {"clinician_id": clinician.id, "name": clinician.name, "credential": clinician.credential, "licence_state": review.patient_state.upper(), "at": datetime.now(UTC).isoformat(), "edited_ai_draft": version.ai_drafted}
