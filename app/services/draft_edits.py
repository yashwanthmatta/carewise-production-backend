import json

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.models.carewise import DraftEdit, LabPacket

# Every doctor save or approval of a DocBridge draft becomes a stored (original, edited)
# pair. The edit distance is worked out here from the stored draft, never taken from
# the browser.
DEFAULT_MODEL_VERSION = "docbridge-rules-v1"
DEFAULT_PROMPT_VERSION = "docbridge-draft-v1"


def word_edit_distance(a: str, b: str) -> int:
    """Word-level Levenshtein distance: insertions, deletions and substitutions of words."""
    x, y = a.split(), b.split()
    if len(x) < len(y):
        x, y = y, x
    previous = list(range(len(y) + 1))
    for i, word in enumerate(x, 1):
        current = [i]
        for j, other in enumerate(y, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != other)))
        previous = current
    return previous[-1]


def draft_document(summary: str, questions: list[str]) -> str:
    text = summary.strip()
    if questions:
        text += "\n\nQuestions for the visit:\n" + "\n".join(f"- {q}" for q in questions)
    return text


def _questions(encrypted: str) -> list[str]:
    try:
        return json.loads(decrypt_field(encrypted)) if encrypted else []
    except ValueError:
        return []


def record_draft_edit(db: Session, packet: LabPacket, doctor_id: str, summary: str, questions: list[str], approved: bool) -> DraftEdit:
    original_summary = decrypt_field(packet.encrypted_draft).strip() if packet.encrypted_draft else ""
    original_questions = _questions(packet.encrypted_draft_questions)
    summary = summary.strip()
    questions = [q.strip() for q in questions if q.strip()]
    original = draft_document(original_summary, original_questions)
    edited = draft_document(summary, questions)
    distance = word_edit_distance(original, edited)
    edit = DraftEdit(
        packet_id=packet.id,
        clinic_id=packet.clinic_id,
        doctor_id=doctor_id,
        event="approve" if approved else "save",
        encrypted_original_text=encrypt_field(original),
        encrypted_edited_text=encrypt_field(edited),
        edited_sections=json.dumps({"summary": summary != original_summary, "questions": questions != original_questions}),
        edit_distance=distance,
        zero_edit_approval=int(approved and distance == 0),
        model_version=packet.model_version or DEFAULT_MODEL_VERSION,
        prompt_version=packet.prompt_version or DEFAULT_PROMPT_VERSION,
    )
    db.add(edit)
    return edit
