# Security And Privacy Review Checklist

This checklist must be completed before real patient data is collected.

## Identity And Access

- MFA for all staff and clinicians.
- Role-based access for patient, clinician, admin, support, and auditor roles.
- Break-glass access flow with approval and audit.
- Session expiration and refresh-token rotation.
- Account lockout and credential stuffing protection.

## Health Data Protection

- Field-level encryption for sensitive patient fields.
- No protected health data in application logs.
- No protected health data in URLs or analytics events.
- Data export and deletion workflows.
- Data retention schedule.
- Regional data residency review.

## Infrastructure

- Secrets stored in a cloud secret manager.
- TLS everywhere.
- Private database networking.
- WAF and rate limits.
- Daily encrypted backups.
- Backup restore drills.
- Dependency and container scanning.

## AI Safety And Privacy

- No raw identifiable health data sent to AI providers unless contract and settings are approved.
- Store prompt/model/source versions.
- Emergency safety does not depend on AI availability.
- Human review for high-risk outputs.
- Block medication-change advice and cure claims.

## Incident Response

- Breach notification playbook.
- Clinical safety incident playbook.
- Security incident severity levels.
- On-call rotation.
- Post-incident review process.

## Required Professional Review

- Healthcare counsel.
- Privacy counsel.
- Security engineer.
- Licensed clinician.
- Pharmacist for medication workflows.
- Dietitian for nutrition workflows.
