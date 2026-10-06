from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role: str = "patient"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetRequestOut(BaseModel):
    status: str
    delivery_status: str
    reset_token: str = ""


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=16)
    new_password: str = Field(min_length=12)


class EmailVerificationRequestOut(BaseModel):
    status: str
    delivery_status: str
    verification_token: str = ""


class EmailVerificationConfirmIn(BaseModel):
    token: str = Field(min_length=16)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"


class RefreshTokenIn(BaseModel):
    refresh_token: str = Field(min_length=16)


class UserSessionOut(BaseModel):
    id: str
    email: EmailStr
    role: str
    email_verified: bool


class PatientProfileIn(BaseModel):
    name: str = ""
    date_of_birth: str = ""
    sex_at_birth: str = ""
    conditions: str = ""
    allergies: str = ""
    location_region: str = ""
    insurance_status: str = ""


class ConsentIn(BaseModel):
    consent_type: str = "care_planning"
    version: str
    accepted: bool
    region: str = ""
    source: str = "web"


class MedicationIn(BaseModel):
    name: str
    dose: str = ""
    timing: str = ""
    refill_date: str = ""
    notes: str = ""


class IntakeIn(BaseModel):
    patient_id: str
    symptom_text: str
    goals: list[str] = []
    diet_style: str = ""
    activity_level: str = ""


class CarePlanOut(BaseModel):
    id: str
    patient_id: str
    risk_level: str
    status: str
    emergency_flags: list[str]
    matched_conditions: list[str]
    recommendation: dict


class ReviewDecisionIn(BaseModel):
    status: str = Field(pattern="^(approved|needs_changes|closed)$")
    clinician_note: str = ""


class QueueJobOut(BaseModel):
    job_id: str
    status: str


class ReportUploadIn(BaseModel):
    patient_id: str
    file_name: str = ""
    content_type: str = ""
    report_text: str = ""
    storage_url: str = ""


class ReportUploadOut(BaseModel):
    id: str
    patient_id: str
    file_name: str
    status: str
    content_type: str = ""
    storage_url: str = ""
    file_size_bytes: int = 0


class ReportTextUpdateIn(BaseModel):
    report_text: str = Field(min_length=1, max_length=12000)


class ReportDownloadOut(BaseModel):
    report_id: str
    file_name: str
    download_url: str
    expires_in_seconds: int


class ReportAnalysisOut(BaseModel):
    id: str
    report_id: str
    patient_id: str
    risk_level: str
    status: str
    summary: dict
    recommendations: dict


class LabTrendIn(BaseModel):
    patient_id: str
    report_id: str | None = None
    test_name: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=80)
    unit: str = Field(default="", max_length=80)
    observed_on: str = Field(default="", max_length=40)
    flag: str = Field(default="not_sure", max_length=80)
    notes: str = Field(default="", max_length=2000)
    source: str = Field(default="manual", max_length=80)


class LabTrendOut(BaseModel):
    id: str
    patient_id: str
    report_id: str | None = None
    test_name: str
    value: str
    unit: str
    observed_on: str
    flag: str
    notes: str
    source: str
    created_at: datetime


class AnalyzeReportRequest(BaseModel):
    report_id: str


class RecommendationRequest(BaseModel):
    patient_id: str
    context_text: str = ""
    diet_style: str = "flexible"
    goals: list[str] = []


class RecommendationOut(BaseModel):
    patient_id: str
    diet: list[str]
    habits: list[str]
    safety_notes: list[str]


class DoctorSearchOut(BaseModel):
    location: str
    specialty: str
    results: list[dict]
    disclaimer: str


class InsuranceMatchIn(BaseModel):
    location_region: str = ""
    conditions: str = ""
    medication_needs: str = ""
    budget_level: str = "mid"


class InsuranceMatchOut(BaseModel):
    matches: list[dict]
    disclaimer: str


class SubscriptionCheckoutIn(BaseModel):
    plan_code: str = Field(pattern="^(basic|plus|premium)$")
    payment_provider: str = "manual"


class SubscriptionPlanOut(BaseModel):
    plan_code: str
    name: str
    monthly_price_usd: int
    summary: str
    features: list[str]


class SubscriptionCheckoutOut(BaseModel):
    id: str
    plan_code: str
    status: str
    checkout_url: str


class SubscriptionMeOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    payments_enabled: bool
    can_manage_billing: bool


class BillingPortalOut(BaseModel):
    portal_url: str


class NotificationDeviceIn(BaseModel):
    channel: str = "push"
    device_token: str = ""
    enabled: bool = True


class NotificationPreferenceOut(BaseModel):
    id: str
    channel: str
    enabled: bool


class DataDeletionRequestIn(BaseModel):
    reason: str = ""


class DataDeletionRequestOut(BaseModel):
    id: str
    status: str


USAGE_EVENTS = (
    "report_explained",
    "sample_opened",
    "demo_started",
    "demo_finished",
    "pdf_read",
    "photo_read",
    "doctor_brief_opened",
    "spanish_used",
    "early_access_opened",
)
SIGNAL_SOURCES = ("web", "mobile")
EARLY_ACCESS_ROLES = ("caregiver", "patient", "clinician", "other")


class UsageEventIn(BaseModel):
    name: str = Field(max_length=60)
    source: str = Field(default="web", max_length=20)


class FeedbackIn(BaseModel):
    helpful: bool
    comment: str = Field(default="", max_length=500)
    source: str = Field(default="web", max_length=20)


class EarlyAccessIn(BaseModel):
    email: EmailStr
    role: str = Field(default="other", max_length=40)
    note: str = Field(default="", max_length=500)
    consent: bool
    source: str = Field(default="web", max_length=20)


class FeedbackCommentIn(BaseModel):
    comment: str = Field(min_length=1, max_length=500)


class SignalAccepted(BaseModel):
    ok: bool = True
    id: str | None = None


class AssistantTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class AssistantChatIn(BaseModel):
    messages: list[AssistantTurn] = Field(min_length=1, max_length=12)
    # Only sent when the person ticks "share my result with the helper".
    report_summary: str = Field(default="", max_length=4000)
    language: str = Field(default="en", pattern="^(en|es)$")
    source: str = "web"


class AssistantChatOut(BaseModel):
    reply: str
    model: str


class DoctorShareIn(BaseModel):
    # The summary the family chose to share, built on their device (values, findings,
    # questions, health record). Shown read-only to whoever has the link.
    snapshot: dict
    label: str = Field(default="", max_length=80)
    days: int = Field(default=7, ge=1, le=30)


class DoctorShareOut(BaseModel):
    id: str
    label: str
    expires_at: datetime
    revoked: bool
    view_count: int
    last_viewed_at: datetime | None
    created_at: datetime | None


class DoctorShareCreatedOut(DoctorShareOut):
    token: str


class DoctorShareViewIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class DoctorShareViewOut(BaseModel):
    label: str
    snapshot: dict
    expires_at: datetime
    created_at: datetime | None
