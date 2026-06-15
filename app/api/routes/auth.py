from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.carewise import User
from app.schemas.carewise import LoginRequest, SignupRequest, TokenResponse
from app.services.audit import write_audit

router = APIRouter()


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()
    write_audit(db, user.id, "", "user_created", "user", user.id, {"role": user.role})
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.email, user.role))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login.")
    write_audit(db, user.id, "", "user_login", "user", user.id, {})
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.email, user.role))
