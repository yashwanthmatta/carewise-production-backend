from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.schemas.carewise import ReviewDecisionIn
from app.services.clinical_review import list_review_queue, review_care_plan

router = APIRouter()


@router.get("/queue")
def queue(
    user: CurrentUser = Depends(require_roles(Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    return {"items": list_review_queue(db, limit=limit, offset=offset)}


@router.post("/{care_plan_id}/review")
def review(
    care_plan_id: str,
    payload: ReviewDecisionIn,
    user: CurrentUser = Depends(require_roles(Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    plan = review_care_plan(db, care_plan_id, payload, user.user_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Care plan not found.")
    return {"id": plan.id, "status": plan.status, "reviewed_at": plan.reviewed_at}
