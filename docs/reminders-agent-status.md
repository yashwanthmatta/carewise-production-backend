# Reminders agent status

Read this first at the start of every reminders run. Update it at the end.

Last run: 2026-10-25 (daily run, 13:56 UTC). Previous: 2026-10-23. Code checked: backend `07f9aa2`, frontend `8d6e756`, mobile `a1a0ce3`.
Clinical rules seen: candidate `2026-10-20.2`, live rules `2026-10-20.5` (frontend `script.js`).
Reminder work never touches clinical rules.

## What exists today

| Feature | Where | State |
|---|---|---|
| Medicine-time reminders (times, weekdays, time zone) saved to the account | backend `app/api/routes/reminders.py`, web `reminders.js`, mobile `src/RemindersScreen.tsx` | Working, tested |
| "Taken" button, today's list (upcoming, due, taken, not confirmed) | all three | Working, tested |
| Phone-call reminders through Twilio, with a "press 1 to agree" first call | backend | Built, off until Twilio is set up |
| Email to the account owner when a reminder is not confirmed | backend | Built, needs email settings |
| Calendar file (.ics) download | web `reminders.js` | Working; fixed in frontend PR (see below) |
| 5-minute scheduler | `.github/workflows/scheduled-jobs.yml` calls `POST /reminders/dispatch` | Running |
| "Reminder planner" (check-ins, refills, follow-ups) | web `index.html`, `script.js` | Separate, saved only in the browser, no alerts |
| Doctor appointment, lab follow-up, visit-prep reminders | none | Not built |
| Phone notifications (iOS, Android) | none | Not built: the mobile app has no notification library |
| Browser notifications | none | Not built |
| Caregiver sharing | `carewise-frontend/docs/caregiver-sharing-plan.md` | Plan only. Do not enable without approval |

## How reminders are sent today

1. GitHub Actions calls `/reminders/dispatch` every 5 minutes (GitHub can run it late).
2. The API makes one event per reminder time per day. A unique key (reminder, kind, time) stops duplicates.
3. If phone calls are on and the person agreed, it calls, waits 10 minutes, calls again, then waits 15 minutes.
4. With no "1" pressed (or no "Taken" tap within 60 minutes for app-only reminders), it marks the time "not confirmed" and emails the owner, once.

Status words the API uses: `due`, `calling`, `taken`, `missed`, `stopped`.
There is no "delivered" status, and the app never claims a call rang. `attempts` counts tries.
Twilio's own delivery result (rang, busy, no answer) is not read yet.

## Fixed in this run

- **Website calendar file showed the medicine label on the lock screen.** The event title used the reminder label and the person's name. Now it says only "FollowThrough Health reminder". Frontend PR on branch `claude/agent-reminders`.
- **Calendar times used the phone's time zone, not the reminder's.** Now pinned with `TZID`. Same PR.
- **Weekday reminders added an extra one today** when today was not a chosen day. Same PR.
- **Email said "we called" even when Twilio refused the call.** Now "we tried to call". The dispatcher also reports `call_failures`. Backend PR on branch `claude/agent-reminders`.
- **Reminder health check.** New `GET /reminders/health` (cron token, counts only) and an hourly workflow `reminders-health.yml` that fails when a reminder is still open 2 hours after its time. Backend PR #44.
- **Added tests** for daylight saving (fall back: one reminder, not two; spring forward: one reminder at 3:30), for reminders in another time zone than the server, and for Twilio failures.

## Known problems (highest first)

0. **Critical: the "every 5 minutes" scheduler runs only every 1 to 5 hours.** GitHub delays scheduled jobs on busy days. Scheduled Jobs runs on 24 and 25 Oct (UTC): 12:03, 13:39, 16:59, 19:24, 21:44, 23:47, 01:46, 06:59, 12:30, 12:36. A reminder time gets an event only if the scheduler runs within 15 minutes after it, so most reminder times are skipped: no call, no "not confirmed" email. The hourly health check now counts these (`skipped_times`) and will turn red once this change is deployed. Real fix needs your approval: a dependable scheduler (see "Needs your approval").
1. **High: no real phone notifications.** The mobile app only shows a list. Nothing alerts the phone unless phone calls or the calendar file are used.
2. **High: two separate reminder features on the website.** "Medicine reminders" (account) and "Reminder planner" (browser only, no alerts). Confusing, and planner items are lost when the browser is cleared.
3. **Medium: Twilio failures are not alerted.** `call_failures` shows only in the Actions log. A stopped scheduler is now caught by the hourly health check (after #44 is merged and deployed).
4. **Medium: Twilio call result is not read.** The app cannot tell "rang" from "accepted by Twilio".
5. **Medium: no snooze, no completed history, no appointment or lab follow-up reminder types.**
6. **Low: the scheduler depends on GitHub Actions timing,** which can lag by several minutes at busy times.

## Privacy checks

- Call script never says medicine names or doses (tested).
- Missed email never includes the reminder label (tested).
- Calendar file now uses generic words only (tested).
- Label, person, phone and caller name are encrypted in the database.
- Twilio webhooks check Twilio's signature. The dispatcher needs the cron token.
- Logs hold only the event ID, never names or numbers.

## Monitoring

- `scheduled-jobs.yml`: every 5 minutes. A failed request makes the run fail (red in GitHub Actions).
- The dispatch reply includes `created`, `calls`, `call_failures`, `missed`. These are counts only, with no health data.
- `reminders-health.yml` (live since #44 merged; verified 2026-10-24 23:23 UTC, reply `healthy: true, stuck_events: 0`): every hour, calls `GET /reminders/health`. Fails when `stuck_events` or `skipped_times` (reminder times in the last 3 hours that never got an event) is above 0. GitHub shows a red run, and can email you, depending on your GitHub notification settings.
- Not yet: an alert when `call_failures` is high.

## Phone testing

Nothing has been tested on a physical phone. Do not mark any item passed until it has been.

**iPhone checklist (when notifications are built)**
- [ ] Permission prompt appears only after the person taps "Turn on reminders".
- [ ] "Don't allow" leaves the app usable and explains how to turn notifications on later.
- [ ] Notification fires with the app closed, after a restart, and in airplane mode (local notification).
- [ ] Lock screen shows "FollowThrough Health: You have a reminder." only.
- [ ] Editing or deleting a reminder removes the old notifications (no duplicates).
- [ ] Changing the phone's time zone and a daylight-saving change keep the right local time.
- [ ] Sign out removes all scheduled notifications.
- [ ] Reinstall: nothing fires until the person signs in again.

**Android checklist (when notifications are built)**
- [ ] Android 13 and later: notification permission is asked at the right moment.
- [ ] A named notification channel ("Reminders") that the person can turn off.
- [ ] Fires with the app closed, after a restart, and with battery saver on.
- [ ] Exact alarm permission is not required, or is explained if used.
- [ ] Same lock-screen, edit, delete, time-zone, sign-out and reinstall checks as iPhone.

**Website and calendar file**
- [ ] Import the .ics into Apple Calendar, Google Calendar and Outlook. Times match the reminder's time zone.
- [ ] Alert on a locked phone shows only generic words.

## Automation

- 5-minute reminder scheduler and nightly cleanup: GitHub Actions `scheduled-jobs.yml` (running).
- Hourly reminder health check: GitHub Actions `reminders-health.yml` (running and reaching the live API).
- Daily agent run: Claude scheduled task "FollowThrough reminders daily run", 13:55 UTC, into the original reminders session (which has the repos and GitHub access). The first version started empty sessions with no repo and did nothing on 2026-10-24; replaced on 2026-10-25.
- Reminder delivery never depends on Claude: it runs on GitHub Actions and the API.

## Needs your approval

- **A dependable scheduler for reminders (most urgent).** GitHub's schedule is too late for medicine times. Options: a Render cron job running `python scripts/dispatch_reminders.py` every 5 minutes (a paid Render feature; check the price in Render first), or a paid always-on API service with an in-process timer. Nothing was bought or set up.
- Turning on Twilio calls or reminder emails for real users.
- Adding a phone notification library to the mobile app (new permission, store disclosure changes).
- Any database change (for example a column for Twilio's call result).
- Medication-specific features, caregiver sharing, or new reminder vendors.

## Next three tasks

1. Once a scheduler is approved: set it up as a Render cron job (the script already exists), then confirm `skipped_times` stays 0 for a day.
2. Design note and mockup: one reminder list on the website (merge the planner into account reminders), with appointment and lab follow-up types that need a user-confirmed date.
3. Plan local notifications for iOS and Android (Expo notifications), with the checklists above. Needs approval before adding the library.
