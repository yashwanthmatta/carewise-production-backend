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


class ReportAnalysisOut(BaseModel):
    id: str
    report_id: str
    patient_id: str
    risk_level: str
    status: str
    summary: dict
    recommendations: dict


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
