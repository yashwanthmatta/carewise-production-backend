# Voice and audio: status

Kept by the voice and audio agent. Plain words. Updated 2026-10-25.
Only things that were actually built and tested are listed as done.

## What exists today

| Where | Feature | State |
|---|---|---|
| Website | **Listen** button on a report (browser's own voice, 0.9 speed, English or Spanish) | Live before this work. Fixed in frontend PR #109 (merged 2026-10-24) |
| Website | Lab values said in words with the same meaning (`spokenText` in `script.js`) | Merged (frontend #109) and live; checked on the live site 2026-10-25 |
| Mobile app | **Listen** button on the report screen (phone's own voice, `expo-speech`) | Pull request open: mobile #48 |
| Backend | Medicine reminder phone calls (Twilio Polly voices, keypad answers) | Live. Clearer scripts merged in backend #25. Spanish fixes in the backend PR for this work |
| Ads | Voiceover scripts and subtitles for 4 campaigns | Drafts in `docs/voice-ads/`, not approved, not published |
| Microphone | None anywhere. The website blocks it (`Permissions-Policy: microphone=()`) | Correct; leave it off |

The rules version on the website and in the app is `2026-10-20.5`. Voice work did not change any
clinical wording, urgency rule or rules version.

## Safety rules the voice features follow

- Nothing is spoken until the person presses Listen. The mobile app also stops speaking on a new
  report, a language switch, another screen, or when the app goes to the background.
- Speech is made on the device. No report text is sent to any voice service.
- Only numbers, units and symbols next to a number are rewritten for speech. Words such as "not",
  "may" or "urgent" are never changed. A unit the code does not know is read as written.
- Decimals are said digit by digit after the point ("0.04" is "0 point 0 4"), so a voice cannot
  turn it into "point four".
- In Spanish, 10^9 is "mil millones", never "billón" (a thousand times larger).
- Reminder calls never name a medicine or a dose.

## Tests

| Test | Where | Runs |
|---|---|---|
| `scripts/eval/speech-cases.mjs`: 36 exact cases, number and negation round-trip on 8 synthetic reports, Listen pressed end to end | frontend | Every PR (Frontend CI), nightly (Audio QA workflow) |
| `scripts/speech_cases_check.js`: same 36 cases plus Listen order on 8 reports | mobile | Every PR (`npm run ci:check` in Mobile CI) |
| `tests/test_reminders.py`: call scripts say who is calling, how to stop and repeat, no medicine words, slow rate, pause, 10-second wait | backend | Every PR (Backend CI) |
| `tests/test_voice_ads.py`: ad lengths fit 15 or 30 seconds, speaking and caption speed, banned claims, English and Spanish timing match, subtitles match the spoken words | backend | Every PR (Backend CI) |

The tests are what was run. No real-device listening has been done yet.

## Automation

- **Audio QA** (`carewise-frontend/.github/workflows/audio-qa.yml`) runs nightly at 07:23 UTC and on
  demand. It checks read-aloud wording on `main`, then read-only on the live website once the
  wording is deployed. It uses synthetic reports and blocks any network call outside the site.
- The other checks run on every pull request inside the existing CI workflows.

## Known gaps (backlog, most important first)

1. **Real-device listening.** iPhone Safari, Android Chrome, the iOS and Android apps, English and
   Spanish, speaker and earbuds, low volume. Needs a person with the phones.
2. **Spanish review** of the reminder calls, the unit words and the ad scripts, by a qualified
   language reviewer.
3. **Pause, resume and speed control** for Listen (today it only has start and stop, at 0.9 speed).
4. **Read one result** instead of the whole report.
5. **Numbers with a thousands comma** ("1,234") are left as written. A Spanish voice may read the
   comma as a decimal point. Needs a decision on how the reader handles commas before changing it.
6. **Blood pressure "186/124"** is left as written; most voices say "slash". Could become
   "186 over 124" after review.
7. **Reminder calls:** a real Twilio test call has not been made (needs the founder's Twilio
   account). Neural Polly voices could sound warmer; check the price first.
8. More ad concepts from the brief not drafted yet: Spanish family explanation, product discovery,
   free sample demo, "The Report / In Plain Words".
9. Voice commands ("Read my summary", "Stop reading") are research only. They need the microphone,
   so they need a privacy and consent review before any work.

## Last automated run

- 2026-10-25, Audio QA run 1 (started by hand), on `main` and on the live website
  https://followthroughhealth.com: **passed**, 36 read-aloud cases and 8 reports each. This shows
  the read-aloud fix is live. Run: https://github.com/yashwanthmatta/carewise-frontend/actions/runs/40147511673

Add later runs here only when they actually happened.
