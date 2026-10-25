# Fix verification register (independent fix check)

Maintained by the independent reviewer. Each fix is re-tested by trying to break it with
synthetic inputs, never by trusting a merged PR or green CI. Statuses: VERIFIED FIXED,
PARTIALLY FIXED, REGRESSED, STILL BROKEN, NOT TESTED, REQUIRES HUMAN REVIEW.

## Reviewed heads (latest run 2026-10-25)

| Repo | Commit | What |
|---|---|---|
| backend `main` | `c3bc075` | 142 tests pass, ruff clean (run on `claude/agent-reviewer` `856314e`, which contains `main`) |
| frontend PR #114 head | `42fac59` | rules 2026-10-20.6 |
| mobile PR #46 head | `b5b6a29` | rules 2026-10-20.6 mirror |
| backend live on Render (2026-10-23) | `07f9aa2` | was `main` at that time |
| frontend live on Render (2026-10-23) | `8d6e756` | was `main` at that time; rules .5 |

## Register

| ID | Original defect | Fix | Verification | Status | Remaining risk / next action |
|---|---|---|---|---|---|
| SR-1 | Emailed labs with a generic subject shared one patient code, mixing two patients' Q&A and history | backend #27 (`patient_ref_from`, later REF-only `EXPLICIT_REF`) | 17 subjects tried. "DEID lab results", "DEID A1C results", "DEID Vitamin B12", "DEID labs 10/14", "DEID CMP-14" and "Fwd: DEID labs" each get their own code. "DEID REF-2201" and "Re: Fwd: DEID REF-2201" give REF-2201. The first version of #27 still gave A1C/B12/T4/dates as codes; fixed in `f5987cb` | VERIFIED FIXED | Clinics must use the `REF-1234` format |
| SR-2 | Patient Q&A filter let diagnosis, reassurance and medicine names through; Q&A always on | #27 + `2d2d9c8`: owner opt-in, second model check that fails closed, global `PATIENT_QA_SAFETY_VERIFIED` switch (default off) | 34 answers tried: 32 unsafe, 2 legitimate. 30 of the unsafe ones are deflected and the 2 legitimate ones are answered, including brand names, "This is normal", "Your kidneys are fine" and "You've got prediabetes". "All good here." and "You are in great shape." pass the word filter; the second model check and the off-by-default switch cover them. A non-owner can't turn Q&A on (403); the patient endpoint returns 403 when it's off | VERIFIED FIXED (layered) | Run the real-model safety check before setting the switch; the word list will never be complete |
| SR-3 | Rate limits trusted a fake first X-Forwarded-For | #27 `client_address` (rightmost public hop) + per-account limits | Fake chains are ignored. 12 two-step guesses from 12 fake addresses: refused (429) from attempt 9 on. Login stops at 20 per account | VERIFIED FIXED | Confirm with one real request that Render's last hop is the visitor, not a shared proxy. Per-account limit lets anyone lock out a known email for 15 min (accepted trade-off) |
| SR-6 | Password reset left old sessions signed in | #27 `revoke_sessions` on reset and 2-step on/off | Old refresh token returns 401 after reset and after turning 2-step on | PARTIALLY FIXED | Old 30-minute access tokens still work after reset (`/auth/me` returned 200). Fix: per-user token version. Not a patient-safety risk; owner decision |
| SR-7 | Privacy pages didn't describe Q&A | frontend #49 | Pages read: what is sent to Anthropic, identifiers removed, encrypted storage, deletion | VERIFIED FIXED | — |
| R5 | "Vitamin D, 25-hydroxy" with no result read as vitamin D 25 | rules .5 (frontend #99, mobile #38) | Fixed for "25-hydroxy". **But D2/D3 forms still broke on live `main`**: "Vitamin D3 25 ng/mL" read 3, "Vitamin D2+D3 (25-OH) 41 ng/mL" read 2 ("Needs attention"), "Vitamin D3 / Pending" invented 3 | PARTIALLY FIXED on `main` | Fixed in .6 below; live site still has the D3 bug until #114 and #46 merge |
| R6-1 | D2/D3 digit read as the vitamin D result | .6 fix 1 (frontend `35e70d4`, mobile `b4bf146`, in #114/#46) | 6 web cases and 3 app cases fail on .5 and pass on .6. 160 review cases: 0 changed. Web and app give the same values | VERIFIED FIXED (not merged) | Needs owner approval and clinician sign-off |
| R6-2..6 | Repeated test lost its concerning value; OCR-glued numbers (`S.9`, `1O8`); blank result took range low end; date read as range; bare `<100` read as result | .6 fixes 2–6 (other session) | Re-tried on #114 head: `S.9`, `1O8`, blank potassium, `LDL <100` give no value; `LDL 151 <100 H` reads 151. All CI evals pass locally: 68-report accuracy 100%, 34 safety cases, photo correction, headings, repeat/misread, 10,000 stress reports, smoke | VERIFIED FIXED (not merged) | New "More than one result" wording needs clinician approval |
| N-A1C-1 | `Hemoglobin A1c 59 %` accepted as A1C 59% (impossible value) | none | Reproduced on .5 and .6, web and app. Shown as "Clinician review important", not reassurance | STILL BROKEN | Add a plausibility cap (e.g. >20% = "could not read"). Changes extraction: needs a rules version and clinician review |
| N-A1C-2 | `Hemoglobin A1c .59` with no unit read as 59 mmol/mol, shown as an invented 7.5% | none | Reproduced on .5 and .6, web and app | STILL BROKEN | Only convert mmol/mol when the unit is printed. Same approval path |
| N-DEID | Training export and Q&A cleaning missed "First Last, your…", YYYY/MM/DD and "Oct 3" | backend `856314e` (other session, no PR yet) | 142 tests pass, ruff clean. Tried: "Maria Lopez, your A1c" → "[NAME], your A1c"; "2026/10/03" → "2026"; "Oct 3" → "[DATE]"; lab lines unchanged. "LDL 151 on 10/3" keeps "10/3" | PARTIALLY FIXED | Month/day without a year in numbers ("10/3") still passes; ambiguous with ratios, low priority |

## Production checks (2026-10-23, via Render; this container cannot reach the public site)

- Live deploys: backend `07f9aa2` and frontend `8d6e756` were `main` at the time; both status `live`.
- Direct HTTPS checks (domain, www redirect, http→https, TLS, `/health`) could not run here: the
  proxy refuses the connection (403). The repos' own `production-monitor` and live browser-check workflows cover them.

## Not tested in this run

Physical iPhone/Android testing, release builds, store submission, TLS certificate details.
No claim of App Store or Google Play readiness is made here.
