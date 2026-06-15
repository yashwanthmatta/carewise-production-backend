# Scale Guardrail Check

This checklist maps the 1B-readiness principles to current product design.

## Do Not Hardcode Single-Region Assumptions

Current support:

- Patient profiles include `location_region`.
- Consent records include `region`.
- Deployment docs require regional data residency review before expansion.

Still needed:

- Region-aware routing.
- Regional databases.
- Regional object storage and queues.
- Region-aware key management.

## Do Not Mix Analytics And Patient Records

Current support:

- Production scaffold has transactional patient models only.
- Architecture docs require a separate de-identified analytics lakehouse.

Still needed:

- Dedicated analytics pipeline.
- De-identification process.
- Analytics access controls.

## Do Not Make AI Mandatory For Safety

Current support:

- Emergency red-flag rules are deterministic in `app/services/safety.py`.
- Care-plan generation uses rules before any future AI layer.

Still needed:

- AI gateway with circuit breakers.
- Safety-rule release process.
- Model rollback process.

## Do Not Store Health Data In Logs

Current support:

- Security checklist bans protected health data in application logs, URLs, and analytics events.
- Audit events store metadata, not raw symptom text.

Still needed:

- Structured logging filters.
- DLP scanning.
- Log redaction tests.

## Do Not Skip Audit Trails

Current support:

- `AuditEvent` model exists.
- Auth, profile, medication, care-plan, consent, and clinical-review actions write audit events.

Still needed:

- Immutable audit storage.
- Audit export and retention rules.
- Break-glass access audit workflow.

## Do Not Skip Consent History

Current support:

- `ConsentRecord` model exists.
- Consent record API exists.
- Consent history API exists.
- Consent actions write audit events.

Still needed:

- Localized consent versions.
- Consent withdrawal flow.
- Consent enforcement by feature.

## Do Not Skip Clinician Review For High-Risk Cases

Current support:

- `requires_clinician_review` checks emergency flags and high-risk condition categories.
- High-risk plans are marked `pending_review`.
- Clinical review queue and decision routes exist.

Still needed:

- Broader high-risk taxonomy.
- Clinician assignment.
- Review SLA alerts.
- Escalation workflow.
