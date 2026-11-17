# Lab testing architecture

**Status (17 Nov 2026): stage 1, code and tests with synthetic data only.**
- Nothing is live. `app/services/lab_testing.LIVE` is a code constant set to `False`, so configuration cannot switch it on.
- There are no database tables yet, so merging this changes no production data.
- No partner is connected, no payment is taken, and no order can leave the service.

## Stages

Do not skip stages.

### Stage 1: technical foundation (this PR)
- A synthetic catalog, grouped by health topic.
- The partner and location model, and the adapter interface.
- Eligibility rules that deny by default.
- The order state machine.
- Result import that keeps provenance and revisions.
- Clinician review and signing.

### Stage 2: local partner pilot
Owner approval is needed for each step:
- choose candidate local labs, check their services and licences, and negotiate agreements;
- arrange an ordering clinician or service;
- legal review of direct-access testing and clinician-order rules for each launch state;
- security review, including BAAs;
- a partner integration test;
- support and critical-result procedures.

### Stage 3: controlled launch
- Approved locations and real orders.
- Appointment times confirmed by the partner.
- Secure result import.
- Real clinician review.
- Monitoring.

### Stage 4: expansion
- More labs and regions.
- More panels.
- At-home collection, where a partner offers it.

## What the code guarantees

Each guarantee has a test in `tests/api/test_lab_testing.py`.

**Catalog**
- Every test is marked synthetic and unavailable.
- Price, preparation and turnaround stay empty until a partner's own catalog fills them. None of them is invented, and preparation instructions never come from the AI.

**Locations**
- A location is bookable only when it belongs to a partner with a signed agreement, recorded as verified by someone on the team, and the location itself is verified.
- Anything else is an "informational" listing at most.
- Synthetic partners and locations are never bookable.

**Eligibility**
- Requests are denied by default. A request is allowed only by an explicit rule for that state and test, with a recorded legal reviewer.
- Synthetic rules are ignored for real requests.
- When a rule allows both pathways, the clinician pathway is preferred.

**Orders**
- Payment is accepted only after approval, and paying never approves anything.
- Only the assigned clinician can approve, decline or ask for more information. They need a recorded credential and must be licensed in the patient's state.
- The same idempotency key always gives one order.
- A booking counts only when the partner confirms it. A failed booking stays unbooked and can be retried.
- Cancelling after payment records a refund owed.
- States cannot be skipped, and every step goes into the audit trail.
- While lab testing is not live, nothing is sent to any lab. A synthetic run against a synthetic partner is the only exception.

**Results**
- A result is matched only when the lab, the order and the patient reference all agree. A mismatch is refused, never guessed.
- Values, units and ranges are stored exactly as sent.
- Every revision is kept: a corrected result adds a revision and never overwrites.
- A message delivered twice is ignored.
- A preliminary result cannot replace a final one.

**Clinician review**
- An AI draft is never shown to a patient as clinician-reviewed.
- Signing needs access to the patient, a credential and a licence in the patient's state. The signature records who signed, their credential, the state, the time, and whether they edited an AI draft.
- A signed version is never edited in place: a change makes a new version that must be signed again.

## Not built yet, and why

- **Database tables and a migration.** Deploys run migrations on start, so the first lab-testing tables are a production migration. That needs owner approval.
- **Ordering and booking endpoints.** These need a real partner and the ordering arrangement first.
- **Critical-result process.** It must be agreed with the lab and the clinical partner: who is responsible, the escalation path, time limits, coverage, acknowledgements and the fallback. The app, the AI chat and push notifications are never the only channel.
- **HL7 v2 / FHIR parsing.** The format depends on what the partner supports. `LabMessage` is the parsed shape that every parser must produce.
- **Map provider for location search.** Needs owner approval, and a check of its privacy and licence terms.
