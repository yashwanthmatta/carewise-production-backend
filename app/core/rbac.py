from enum import StrEnum

from fastapi import Depends, HTTPException, status

from app.core.security import CurrentUser, get_current_user


class Role(StrEnum):
    PATIENT = "patient"
    CLINICIAN = "clinician"
    ADMIN = "admin"


def require_roles(*roles: Role):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action.",
            )
        return user

    return dependency
