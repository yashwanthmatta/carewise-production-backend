from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role: str = "patient"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
