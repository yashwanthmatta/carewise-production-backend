import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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
    # Two-step sign-in: the authenticator secret (encrypted), whether it is on, the last
    # code step used (so a code works once), and hashes of one-time recovery codes.
    encrypted_totp_secret: Mapped[str] = mapped_column(Text, default="")
    totp_enabled: Mapped[int] = mapped_column(Integer, default=0)
    totp_last_step: Mapped[int] = mapped_column(Integer, default=0)
    recovery_code_hashes: Mapped[str] = mapped_column(Text, default="")
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
    provider_customer: Mapped[str] = mapped_column(String(160), default="")
    # Store subscriptions (Apple, Google) end on a known date; Stripe ones end by webhook.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingEvent(Base):
    """Payment-provider events already applied, so a retried webhook changes nothing twice.

    Holds only provider ids and event types: no card or health data.
    """

    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_billing_events_provider_event"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("bevt"))
    provider: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(120), default="")
    subscription_id: Mapped[str] = mapped_column(String(80), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


# Product signals for learning whether FollowThrough Health helps. None of these tables store
# report text, IP addresses or account ids.
class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("day", "name", "source", name="uq_usage_counters_day_name_source"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("use"))
    day: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(20), default="web")
    count: Mapped[int] = mapped_column(Integer, default=0)


class ProductFeedback(Base):
    __tablename__ = "product_feedback"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("fb"))
    helpful: Mapped[str] = mapped_column(String(10), index=True)
    encrypted_comment: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EarlyAccessSignup(Base):
    __tablename__ = "early_access_signups"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("ea"))
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    encrypted_email: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40), index=True, default="other")
    encrypted_note: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DoctorShare(Base):
    # A read-only, expiring link a patient or caregiver gives to their doctor. Only a
    # hash of the link token is stored, and the shared summary is encrypted.
    __tablename__ = "doctor_shares"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("share"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    encrypted_label: Mapped[str] = mapped_column(Text, default="")
    encrypted_snapshot: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Clinic(Base):
    # DocBridge: a practice that reviews lab explanations before they reach patients.
    __tablename__ = "clinics"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("clinic"))
    name: Mapped[str] = mapped_column(String(160))
    tone: Mapped[str] = mapped_column(String(20), default="friendly")
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    # Patient follow-up questions on approved links; off until the owner turns them on.
    patient_qa_enabled: Mapped[int] = mapped_column(Integer, default=0)
    # Private part of the clinic's lab intake email address (labs+CODE@...).
    intake_code: Mapped[str | None] = mapped_column(String(24), unique=True, index=True, nullable=True)
    # Visit summary options set by the owner: the clinic's own self-pay prices (JSON list of
    # {cpt, name, usd}), sections to hide, and the clinic's coverage checklist.
    self_pay_prices: Mapped[str] = mapped_column(Text, default="[]")
    prices_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visit_options: Mapped[str] = mapped_column(Text, default="{}")
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicMember(Base):
    __tablename__ = "clinic_members"
    __table_args__ = (UniqueConstraint("clinic_id", "user_id", name="uq_clinic_members_clinic_user"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("member"))
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(160), default="")
    role: Mapped[str] = mapped_column(String(20), default="clinician")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabPacket(Base):
    # One lab result explained for one patient. Everything clinical is encrypted; the
    # patient is identified only by a clinic-chosen reference (never an SSN).
    __tablename__ = "lab_packets"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("packet"))
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_ref_hash: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_patient_ref: Mapped[str] = mapped_column(Text)
    lab_date: Mapped[str] = mapped_column(String(10), default="")
    encrypted_markers: Mapped[str] = mapped_column(Text, default="")
    encrypted_summary: Mapped[str] = mapped_column(Text, default="")
    encrypted_questions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), index=True, default="draft")
    created_by: Mapped[str] = mapped_column(String(80), default="")
    approved_by: Mapped[str] = mapped_column(String(80), default="")
    approved_by_name: Mapped[str] = mapped_column(String(160), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encrypted_draft: Mapped[str] = mapped_column(Text, default="")
    edited: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_token_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    # "manual" (added on screen) or "email" (forwarded to the clinic's intake address).
    source: Mapped[str] = mapped_column(String(10), default="manual")
    encrypted_source_text: Mapped[str] = mapped_column(Text, default="")
    file_key: Mapped[str] = mapped_column(String(300), default="")
    # The draft questions as first generated, and what generated the draft, so every
    # later save or approval can be stored as an (original, edited) pair.
    encrypted_draft_questions: Mapped[str] = mapped_column(Text, default="")
    model_version: Mapped[str] = mapped_column(String(80), default="")
    prompt_version: Mapped[str] = mapped_column(String(80), default="")
    patient_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DraftEdit(Base):
    # One doctor save or approval of a draft: the original draft and the doctor's
    # version, a preference pair for improving drafts later. Text stays encrypted and is
    # deleted with its lab (retention or account deletion). draft_id and lab_report_id in
    # the spec are both the LabPacket here.
    __tablename__ = "draft_edits"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("edit"))
    packet_id: Mapped[str] = mapped_column(String(80), index=True)
    clinic_id: Mapped[str] = mapped_column(String(80), index=True)
    doctor_id: Mapped[str] = mapped_column(String(80), default="")
    event: Mapped[str] = mapped_column(String(10), default="save")  # "save" or "approve"
    encrypted_original_text: Mapped[str] = mapped_column(Text, default="")
    encrypted_edited_text: Mapped[str] = mapped_column(Text, default="")
    edited_sections: Mapped[str] = mapped_column(Text, default="{}")
    edit_distance: Mapped[int] = mapped_column(Integer, default=0)
    zero_edit_approval: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(80), default="")
    prompt_version: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PatientQuestion(Base):
    # One patient follow-up question on an approved packet and the reply they got, kept
    # encrypted for safety review and deleted with the packet.
    __tablename__ = "patient_questions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("qa"))
    packet_id: Mapped[str] = mapped_column(String(80), index=True)
    clinic_id: Mapped[str] = mapped_column(String(80), index=True)
    encrypted_question: Mapped[str] = mapped_column(Text, default="")
    encrypted_answer: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[str] = mapped_column(Text, default="[]")
    deflected: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ModelVersion(Base):
    # Which generator wrote a draft. A person changes status; nothing is promoted automatically.
    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    base_model: Mapped[str] = mapped_column(String(120), default="")
    training_pairs_count: Mapped[int] = mapped_column(Integer, default=0)
    training_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="canary")  # canary / prod / retired
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClinicInvite(Base):
    # One-time code a clinic owner gives a colleague to join the practice.
    __tablename__ = "clinic_invites"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("invite"))
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="clinician")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MedicineReminder(Base):
    # A medicine-time reminder a family sets up for themselves or a parent. Names,
    # phone number and label are encrypted. Calls only start after the person who
    # will be called presses 1 on a first "do you agree" call.
    __tablename__ = "medicine_reminders"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("rem"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    encrypted_person: Mapped[str] = mapped_column(Text, default="")
    encrypted_label: Mapped[str] = mapped_column(Text, default="")
    times: Mapped[str] = mapped_column(String(64))
    days: Mapped[str] = mapped_column(String(40), default="daily")
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    language: Mapped[str] = mapped_column(String(5), default="en")
    encrypted_phone: Mapped[str] = mapped_column(Text, default="")
    encrypted_caller_name: Mapped[str] = mapped_column(Text, default="")
    call_status: Mapped[str] = mapped_column(String(20), default="off")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_on_miss: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReminderEvent(Base):
    # One reminder time on one day (kind "dose"), or the first consent call
    # (kind "consent"). The phone keypad answer is matched by a token hash.
    __tablename__ = "reminder_events"
    __table_args__ = (UniqueConstraint("reminder_id", "kind", "due_at", name="uq_reminder_event"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("rev"))
    reminder_id: Mapped[str] = mapped_column(ForeignKey("medicine_reminders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="dose")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(12), default="due", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
