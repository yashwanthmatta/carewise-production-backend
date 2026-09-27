# CareWise Stage Presentation Kit

For presenting CareWise to a large live audience. Use synthetic data only on
stage, and ask the audience to use the sample report rather than their own
health information.

## Countdown

**At least 3 days before**

- [ ] Live API fixed in Render (see `investor_demo_runbook.md`), and the
      `Live Backend Smoke` workflow passes.
- [ ] Frontend PR merged, so the live site has PDF reading, the doctor
      brief, Spanish and caregiver mode. The QR code sends people to the live
      site, so the audience only sees what is merged.
- [ ] Deck placeholders filled: founder name, contact details, market,
      traction, the raise. Remove any slide you cannot back with real numbers.
- [ ] Demo account created in advance.

**The day before**

- [ ] Full rehearsal with a timer, twice.
- [ ] Download `CareWise-backup-demo.mp4` to the presenting laptop and put
      it in the deck or on the desktop.
- [ ] Download the deck as PDF or PPTX as an offline copy.
- [ ] Scan the closing-slide QR code with two different phones.

**One hour before**

- [ ] Open the live site on the presenting laptop and wait for API Online,
      Database Ready, Storage Ready on the home page.
- [ ] Open https://carewise-frontend.onrender.com/#tour and click through
      all 8 steps once, then press Esc. Leave the home page open.
- [ ] Phone on do-not-disturb; laptop notifications off; browser zoom at
      125% so the back rows can read it.

## Five-minute talk track

1. **Cover (20 s).** "Most of us have opened a lab report and not
   understood it. CareWise explains it in plain language."
2. **Problem (40 s).** Jargon, numbers without context, short visits. One
   sourced statistic only.
3. **Solution (30 s).** Upload, explain, score, prepare.
4. **Live demo (2 min).** Press "See a 1-minute demo" and click Next
   through the 8 steps (`investor_demo_runbook.md` has a line to say on
   each). It runs in the browser, so it works even if the server is down.
5. **Why CareWise (30 s).** The doctor brief, the patient's language,
   caregivers.
6. **Trust and safety (20 s).** Educational, not a diagnosis; data export and
   deletion; clinician review queue.
7. **Close (20 s).** The QR code: "Scan it and press See a 1-minute demo."

## If something fails on stage

| Problem | Do this |
| --- | --- |
| Wi-Fi is down | Play `CareWise-backup-demo.mp4` and narrate over it. |
| Home page shows "Waking up" | Keep talking; it switches to Online within a minute. The sample report works meanwhile. |
| Sign-in fails | Skip it. The guided demo, analysis, doctor brief, Spanish and caregiver history work without an account. |
| The doctor brief tab is blocked | Use the guided demo: its step 5 shows the brief inside the page, no pop-up needed. |
| A PDF will not read | Say it looks like a scanned image and use the sample report. |

## Honest answers for Q&A

**"Is this AI? Which model?"**
The explanations come from rules built around common lab markers, not a
chatbot, so the same report always gets the same careful wording and the
app cannot invent medical advice. An AI vision model can read photos of
reports; it is optional and currently switched off in production.

**"Is it a diagnosis?"**
No. CareWise explains results for education and visit preparation, and
sends urgent-sounding symptoms to emergency care and high-risk results to
a clinician.

**"Is my health data safe?"**
The sample report and PDF reading run in your own browser and are not
uploaded. Accounts keep data encrypted, record consent, and let you export
or delete everything. Formal legal, privacy and security reviews are the
next milestone before real patient data.

**"Is it HIPAA compliant?"**
Not yet certified. The reviews and vendor agreements are on the roadmap
before launch. Do not claim compliance.

**"How accurate is it?"**
We test reading and flagging at scale: 1,000 lab report PDFs built from
real public patient values in five lab layouts, all read correctly; 1,000
full blood-panel PDFs (27,000 results) with no false or missed flags and
every critical result routed to "contact your doctor today"; and 616 scan
reports explained with no false alarms. Blood tests are compared with the
range the lab printed. This is not clinical validation; a clinician review
of the wording is the next step.

**"Do you read MRI or CT images?"**
No, on purpose. We explain the radiologist's written report in plain words
and turn phrases like "biopsy is recommended" into questions for the
doctor. Reading images is diagnosis and a regulated medical device.

**"Are the Spanish translations reviewed?"**
They are drafts, marked in the app as pending review by a clinician and a
medical translator.

**"Why not just ask ChatGPT?"**
A chatbot gives a one-off answer. CareWise keeps results over time, gives
the doctor a one-page brief, supports caregivers, and uses fixed, reviewed
wording instead of free text.

## Do not say

- "Diagnoses", "detects disease", "replaces your doctor", "prevents",
  "cures".
- "HIPAA compliant", "clinically validated" or "doctor approved" until it is.
- Any user, revenue or market number you cannot show a source for.
