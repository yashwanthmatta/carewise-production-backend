from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.rbac import Role, require_roles
from app.db.session import get_db
from app.models.carewise import CarePlan, ConsentRecord, PatientProfile, ReportUpload, User

router = APIRouter()


@router.get("/summary")
def admin_summary(
    admin=Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "patients": db.scalar(select(func.count()).select_from(PatientProfile)),
        "care_plans": db.scalar(select(func.count()).select_from(CarePlan)),
        "reports": db.scalar(select(func.count()).select_from(ReportUpload)),
        "consent_records": db.scalar(select(func.count()).select_from(ConsentRecord)),
    }
