import json

from sqlalchemy.orm import Session

from app.models.carewise import AuditEvent


def write_audit(
    db: Session,
    actor_id: str,
    patient_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        patient_id=patient_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=json.dumps(metadata),
    )
    db.add(event)
    return event
