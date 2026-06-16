from fastapi import APIRouter, Depends

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.schemas.carewise import InsuranceMatchIn, InsuranceMatchOut

router = APIRouter()


@router.post("/match", response_model=InsuranceMatchOut)
def match_insurance(
    payload: InsuranceMatchIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
):
    priorities = [
        "primary care network",
        "specialist coverage",
        "prescription formulary",
        "deductible and out-of-pocket maximum",
    ]
    if "diabetes" in payload.conditions.lower():
        priorities.append("endocrinology and glucose supply coverage")
    if "hypertension" in payload.conditions.lower() or "blood pressure" in payload.conditions.lower():
        priorities.append("cardiology and blood pressure medication coverage")
    return InsuranceMatchOut(
        matches=[
            {
                "plan_type": "Marketplace / employer plan comparison",
                "budget_level": payload.budget_level,
                "coverage_priorities": priorities,
                "next_step": "Compare official plan documents and verify doctors/medications before enrollment.",
            }
        ],
        disclaimer="Prototype insurance matching is educational and not licensed insurance advice.",
    )
