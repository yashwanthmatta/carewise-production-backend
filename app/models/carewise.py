import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("user"))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), index=True, default="patient")
    email_verified: Mapped[str] = mapped_column(String(10), index=True, default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    patient_profile: Mapped["PatientProfile"] = relationship(back_populates="user")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("reset"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(80), index=True, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("refresh"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(80), index=True, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("verify"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(80), index=True, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("rate"))
    bucket_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    attempts: Mapped[str] = mapped_column(String(40), default="0")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("patient"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    encrypted_name: Mapped[str] = mapped_column(Text, default="")
    encrypted_date_of_birth: Mapped[str] = mapped_column(Text, default="")
    sex_at_birth: Mapped[str] = mapped_column(String(40), default="")
    encrypted_conditions: Mapped[str] = mapped_column(Text, default="")
    encrypted_allergies: Mapped[str] = mapped_column(Text, default="")
    location_region: Mapped[str] = mapped_column(String(120), index=True, default="")
    insurance_status: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="patient_profile")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("consent"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(80), index=True)
    accepted: Mapped[str] = mapped_column(String(10), default="true")
    region: Mapped[str] = mapped_column(String(120), index=True, default="")
    source: Mapped[str] = mapped_column(String(120), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("med"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    encrypted_name: Mapped[str] = mapped_column(Text)
    encrypted_dose: Mapped[str] = mapped_column(Text, default="")
    encrypted_timing: Mapped[str] = mapped_column(Text, default="")
    refill_date: Mapped[str] = mapped_column(String(40), default="")
    encrypted_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Intake(Base):
    __tablename__ = "intakes"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("intake"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    encrypted_symptom_text: Mapped[str] = mapped_column(Text)
    goals_json: Mapped[str] = mapped_column(Text, default="[]")
    diet_style: Mapped[str] = mapped_column(String(80), default="")
    activity_level: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CarePlan(Base):
    __tablename__ = "care_plans"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("plan"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    intake_id: Mapped[str] = mapped_column(ForeignKey("intakes.id"), index=True)
    risk_level: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(80), index=True, default="pending_review")
    emergency_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    matched_conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    recommendation_json: Mapped[str] = mapped_column(Text, default="{}")
    clinician_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("audit"))
    actor_id: Mapped[str] = mapped_column(String(80), index=True, default="")
    patient_id: Mapped[str] = mapped_column(String(80), index=True, default="")
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), default="")
    resource_id: Mapped[str] = mapped_column(String(80), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportUpload(Base):
    __tablename__ = "report_uploads"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("report"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="")
    storage_key: Mapped[str] = mapped_column(Text, default="")
    storage_url: Mapped[str] = mapped_column(Text, default="")
    file_size_bytes: Mapped[str] = mapped_column(String(40), default="0")
    encrypted_report_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(80), index=True, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportAnalysis(Base):
    __tablename__ = "report_analyses"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("analysis"))
    report_id: Mapped[str] = mapped_column(ForeignKey("report_uploads.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    risk_level: Mapped[str] = mapped_column(String(80), index=True, default="routine")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    recommendations_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(80), index=True, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabTrend(Base):
    __tablename__ = "lab_trends"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("lab"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("report_uploads.id"), index=True, nullable=True)
    test_name: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[str] = mapped_column(String(80), default="")
    unit: Mapped[str] = mapped_column(String(80), default="")
    observed_on: Mapped[str] = mapped_column(String(40), index=True, default="")
    flag: Mapped[str] = mapped_column(String(80), index=True, default="not_sure")
    encrypted_notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(80), index=True, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("sub"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    plan_code: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(80), index=True, default="pending")
    payment_provider: Mapped[str] = mapped_column(String(80), default="manual")
    provider_reference: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("notify"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(80), default="push")
    device_token: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[str] = mapped_column(String(10), default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataDeletionRequest(Base):
    __tablename__ = "data_deletion_requests"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("delete"))
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True, default="")
    status: Mapped[str] = mapped_column(String(80), index=True, default="requested")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("idx_care_plans_patient_created", CarePlan.patient_id, CarePlan.created_at.desc())
Index("idx_care_plans_status_created", CarePlan.status, CarePlan.created_at.desc())
Index("idx_audit_patient_created", AuditEvent.patient_id, AuditEvent.created_at.desc())
Index("idx_consent_user_created", ConsentRecord.user_id, ConsentRecord.created_at.desc())
Index("idx_consent_region_created", ConsentRecord.region, ConsentRecord.created_at.desc())
Index("idx_reports_patient_created", ReportUpload.patient_id, ReportUpload.created_at.desc())
Index("idx_analyses_patient_created", ReportAnalysis.patient_id, ReportAnalysis.created_at.desc())
Index("idx_lab_trends_patient_observed", LabTrend.patient_id, LabTrend.observed_on.desc())
Index("idx_lab_trends_patient_test", LabTrend.patient_id, LabTrend.test_name)
Index("idx_deletion_requests_user_created", DataDeletionRequest.user_id, DataDeletionRequest.created_at.desc())
Index("idx_password_reset_user_created", PasswordResetToken.user_id, PasswordResetToken.created_at.desc())
Index("idx_refresh_tokens_user_created", RefreshToken.user_id, RefreshToken.created_at.desc())
Index("idx_email_verification_user_created", EmailVerificationToken.user_id, EmailVerificationToken.created_at.desc())
Index("idx_rate_limit_action_window", RateLimitBucket.action, RateLimitBucket.window_start.desc())
