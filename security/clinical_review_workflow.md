# Clinical Review Workflow

CareWise should launch as a clinician-reviewed care navigation assistant, not as a diagnosis engine.

## Review Queue Triggers

Send a care plan to clinical review when:

- Emergency red flags are detected.
- Kidney disease is mentioned.
- Heart disease is mentioned.
- Pregnancy is mentioned.
- Cancer support is mentioned.
- Stroke recovery is mentioned.
- Severe allergy is mentioned.
- Mental health crisis language is detected.
- Complex medication list is present.
- Patient is a child, elderly, or otherwise high-risk.

## Review Statuses

- `pending_review`
- `approved`
- `needs_changes`
- `closed`

## Review Actions

Clinician reviewers should be able to:

- See patient summary.
- See red flags.
- See medication/allergy context.
- Approve safe education.
- Request changes.
- Close duplicate or inappropriate items.
- Add a clinician note.
- Trigger patient notification only after approval where required.

## Safety Rule

Emergency guidance must remain visible even if clinician review is delayed.

Routine diet, exercise, insurance, and subscription suggestions must not delay emergency care.
