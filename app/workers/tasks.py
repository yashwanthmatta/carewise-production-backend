from app.db.session import SessionLocal
from app.schemas.carewise import IntakeIn
from app.services.care_plan import create_care_plan


def generate_care_plan_task(actor_id: str, payload: dict) -> str:
    db = SessionLocal()
    try:
        result = create_care_plan(db, actor_id, IntakeIn(**payload))
        return result.id
    finally:
        db.close()
