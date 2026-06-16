from fastapi import APIRouter, Depends

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.schemas.carewise import DoctorSearchOut

router = APIRouter()


@router.get("/search", response_model=DoctorSearchOut)
def search_doctors(
    location: str = "US",
    specialty: str = "primary care",
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
):
    return DoctorSearchOut(
        location=location,
        specialty=specialty,
        results=[
            {
                "name": f"{specialty.title()} clinic near {location}",
                "network_status": "verify_with_insurance",
                "next_step": "Call the clinic and confirm availability, insurance network, and urgent symptoms policy.",
            }
        ],
        disclaimer="Prototype doctor search does not replace verified provider directories or emergency care.",
    )
