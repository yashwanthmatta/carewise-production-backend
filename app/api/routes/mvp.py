from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.routes.auth import login as login_user
from app.api.routes.auth import signup as signup_user
from app.api.routes.patients import get_my_profile
from app.api.routes.reports import analyze_report, create_report_file_upload, list_reports
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.schemas.carewise import AnalyzeReportRequest, LoginRequest, SignupRequest, TokenResponse

router = APIRouter()


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    return signup_user(payload, db)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return login_user(payload, db)


@router.post("/upload-report")
async def upload_report(
    patient_id: str = Form(...),
    report_text: str = Form(""),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return await create_report_file_upload(patient_id, report_text, file, user, db)


@router.post("/analyze-report")
def analyze_report_for_mvp(
    payload: AnalyzeReportRequest,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return analyze_report(payload.report_id, user, db)


@router.get("/report-results")
def report_results(
    patient_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return list_reports(patient_id, user, db)


@router.get("/user-profile")
def user_profile(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return get_my_profile(user, db)
