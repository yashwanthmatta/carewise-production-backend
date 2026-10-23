import hashlib
import hmac
import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import MedicineReminder, ReminderEvent, User
from app.schemas.carewise import ReminderIn, ReminderOut, ReminderTakenIn
from app.services import reminder_calls
from app.services.cron_auth import require_cron_token
from app.services.email_delivery import base_message, send_email
from app.services.rate_limit import check_rate_limit

# Medicine reminders. Families pick times; FollowThrough Health can call the person (after they
# agree on a first call) and email the account owner if a reminder is not confirmed.
# It is a reminder service, not a medical alert, and it never says what medicine.
router = APIRouter()
log = logging.getLogger(__name__)

MAX_REMINDERS = 10
DUE_WINDOW = timedelta(minutes=15)
RETRY_AFTER = timedelta(minutes=10)
GIVE_UP_AFTER = timedelta(minutes=15)
APP_ONLY_MISSED_AFTER = timedelta(minutes=60)
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def event_token(event_id: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), event_id.encode(), hashlib.sha256).hexdigest()[:40]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def due_moments(reminder: MedicineReminder, local_day) -> list[tuple[str, datetime]]:
    # Each reminder time on one local day, as (HH:MM, UTC moment), honoring chosen weekdays.
    days = [day for day in reminder.days.split(",") if day] if reminder.days != "daily" else []
    if days and DAYS[local_day.weekday()] not in days:
        return []
    tz = zone(reminder.timezone)
    moments = []
    for clock in [value for value in reminder.times.split(",") if value]:
        hour, minute = (int(part) for part in clock.split(":"))
        local = datetime(local_day.year, local_day.month, local_day.day, hour, minute, tzinfo=tz)
        moments.append((clock, local.astimezone(timezone.utc)))
    return moments


def new_event(db: Session, reminder: MedicineReminder, kind: str, due_at: datetime, status_value: str = "due") -> ReminderEvent:
    event = ReminderEvent(reminder_id=reminder.id, kind=kind, due_at=due_at, status=status_value, attempts=0, token_hash="")
    event.id = f"rev_{hashlib.sha256(f'{reminder.id}{kind}{due_at.isoformat()}'.encode()).hexdigest()[:32]}"
    event.token_hash = token_hash(event_token(event.id))
    db.add(event)
    db.flush()
    return event


def find_event(db: Session, reminder_id: str, kind: str, due_at: datetime) -> ReminderEvent | None:
    return db.scalar(
        select(ReminderEvent).where(
            ReminderEvent.reminder_id == reminder_id, ReminderEvent.kind == kind, ReminderEvent.due_at == due_at
        )
    )


def reminder_out(db: Session, reminder: MedicineReminder, now: datetime) -> dict:
    today = now.astimezone(zone(reminder.timezone)).date()
    doses = []
    for clock, due_at in due_moments(reminder, today):
        event = find_event(db, reminder.id, "dose", due_at)
        if event:
            state = {"calling": "calling", "due": "due"}.get(event.status, event.status)
        else:
            state = "upcoming" if due_at > now else "past"
        doses.append({"time": clock, "status": state})
    phone = decrypt_field(reminder.encrypted_phone) if reminder.encrypted_phone else ""
    return {
        "id": reminder.id,
        "person": decrypt_field(reminder.encrypted_person),
        "label": decrypt_field(reminder.encrypted_label),
        "times": [value for value in reminder.times.split(",") if value],
        "days": [] if reminder.days == "daily" else [day for day in reminder.days.split(",") if day],
        "timezone": reminder.timezone,
        "language": reminder.language,
        "call": reminder.call_status != "off",
        "phone_last4": phone[-4:] if phone else "",
        "caller_name": decrypt_field(reminder.encrypted_caller_name) if reminder.encrypted_caller_name else "",
        "call_status": reminder.call_status,
        "alert_on_miss": bool(reminder.alert_on_miss),
        "today": doses,
    }


def apply_payload(db: Session, reminder: MedicineReminder, payload: ReminderIn, now: datetime) -> None:
    times = sorted({value.strip() for value in payload.times})
    if not times or not all(TIME_PATTERN.match(value) for value in times):
        raise HTTPException(status_code=422, detail="Use times like 08:00 or 20:30.")
    days = [day for day in DAYS if day in {value.lower()[:3] for value in payload.days}]
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="Unknown time zone.") from None
    reminder.encrypted_person = encrypt_field(payload.person.strip() or "Me")
    reminder.encrypted_label = encrypt_field(payload.label.strip())
    reminder.times = ",".join(times)
    reminder.days = ",".join(days) if days and len(days) < 7 else "daily"
    reminder.timezone = payload.timezone
    reminder.language = payload.language
    reminder.alert_on_miss = int(payload.alert_on_miss)
    old_phone = decrypt_field(reminder.encrypted_phone) if reminder.encrypted_phone else ""
    if not payload.call:
        reminder.call_status = "off"
        reminder.encrypted_phone = ""
        return
    # Leaving the number blank when editing keeps the saved one.
    phone = re.sub(r"[\s().-]", "", payload.phone) or old_phone
    if not PHONE_PATTERN.match(phone):
        raise HTTPException(status_code=422, detail="Enter the phone number with country code, like +1 555 123 4567.")
    needs_consent = phone != old_phone or reminder.call_status in ("off", "stopped")
    if needs_consent and not payload.consent_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that the person agreed to get reminder calls.")
    reminder.encrypted_caller_name = encrypt_field(payload.caller_name.strip())
    reminder.encrypted_phone = encrypt_field(phone)
    if needs_consent:
        # A new number always starts with a "press 1 to agree" call before any reminder call.
        reminder.call_status = "pending_consent"
        reminder.consent_at = None
        db.flush()
        new_event(db, reminder, "consent", now.replace(microsecond=0))


def owned(db: Session, reminder_id: str, user: CurrentUser) -> MedicineReminder:
    reminder = db.get(MedicineReminder, reminder_id)
    if reminder is None or reminder.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return reminder


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    reminders = db.scalars(
        select(MedicineReminder).where(MedicineReminder.user_id == user.user_id).order_by(MedicineReminder.created_at)
    ).all()
    return [reminder_out(db, reminder, now) for reminder in reminders]


@router.post("", response_model=ReminderOut)
def create_reminder(
    payload: ReminderIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    count = db.scalar(select(func.count(MedicineReminder.id)).where(MedicineReminder.user_id == user.user_id))
    if (count or 0) >= MAX_REMINDERS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You can have up to 10 reminders.")
    if payload.call:
        check_rate_limit(db, request, "reminder_call_setup", user.user_id, max_attempts=5, window_seconds=86400)
    now = datetime.now(timezone.utc)
    reminder = MedicineReminder(user_id=user.user_id, times="", active=1)
    db.add(reminder)
    db.flush()
    apply_payload(db, reminder, payload, now)
    db.commit()
    return reminder_out(db, reminder, now)


@router.put("/{reminder_id}", response_model=ReminderOut)
def update_reminder(
    reminder_id: str,
    payload: ReminderIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    reminder = owned(db, reminder_id, user)
    if payload.call:
        check_rate_limit(db, request, "reminder_call_setup", user.user_id, max_attempts=5, window_seconds=86400)
    now = datetime.now(timezone.utc)
    apply_payload(db, reminder, payload, now)
    db.commit()
    return reminder_out(db, reminder, now)


@router.delete("/{reminder_id}")
def delete_reminder(
    reminder_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    reminder = owned(db, reminder_id, user)
    db.execute(delete(ReminderEvent).where(ReminderEvent.reminder_id == reminder.id))
    db.delete(reminder)
    db.commit()
    return {"status": "deleted"}


@router.post("/{reminder_id}/taken", response_model=ReminderOut)
def mark_taken(
    reminder_id: str,
    payload: ReminderTakenIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    reminder = owned(db, reminder_id, user)
    now = datetime.now(timezone.utc)
    moments = due_moments(reminder, now.astimezone(zone(reminder.timezone)).date())
    if payload.time:
        moments = [moment for moment in moments if moment[0] == payload.time]
    else:
        # The latest time that has already come, else the next one today.
        past = [moment for moment in moments if moment[1] <= now + timedelta(minutes=60)]
        moments = past[-1:] or moments[:1]
    if not moments:
        raise HTTPException(status_code=422, detail="No reminder time today to mark.")
    due_at = moments[0][1]
    event = find_event(db, reminder.id, "dose", due_at) or new_event(db, reminder, "dose", due_at)
    event.status = "taken"
    event.confirmed_at = now
    db.commit()
    return reminder_out(db, reminder, now)


@router.post("/{reminder_id}/consent-call", response_model=ReminderOut)
def resend_consent_call(
    reminder_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    reminder = owned(db, reminder_id, user)
    if reminder.call_status != "pending_consent":
        raise HTTPException(status_code=409, detail="This reminder is not waiting for agreement.")
    check_rate_limit(db, request, "reminder_consent_call", reminder.id, max_attempts=3, window_seconds=86400)
    now = datetime.now(timezone.utc)
    new_event(db, reminder, "consent", now.replace(microsecond=0))
    db.commit()
    return reminder_out(db, reminder, now)


# --- Scheduler -------------------------------------------------------------------


def call_for(event: ReminderEvent, reminder: MedicineReminder) -> bool:
    # Returns False when Twilio refused the call. "attempts" counts tries, not calls that
    # rang, so the family email says "we tried to call" rather than "we called".
    event.attempts = (event.attempts or 0) + 1
    event.last_call_at = datetime.now(timezone.utc)
    event.status = "calling"
    try:
        reminder_calls.place_call(
            decrypt_field(reminder.encrypted_phone),
            reminder_calls.public_url(f"/reminders/voice/{event_token(event.id)}"),
        )
    except Exception:  # noqa: BLE001 - a failed call is retried, then counted as missed
        log.exception("Reminder call failed for %s", event.id)
        return False
    return True


def friendly_clock(moment: datetime) -> str:
    # 20:30 -> "8:30 PM", easier to read in an email than a 24-hour time.
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"


def why_not_confirmed(event: ReminderEvent, reminder: MedicineReminder, person: str) -> str:
    # Say what really happened, so the family is not told "we called" when no call went out.
    attempts = event.attempts or 0
    if attempts:
        times = "once" if attempts == 1 else "twice" if attempts == 2 else f"{attempts} times"
        return f"We tried to call {person} {times} and nobody pressed 1 to say it was taken."
    if reminder.call_status == "pending_consent":
        return (
            f"No reminder call was made, because {person} has not yet pressed 1 on the first call to agree to calls. "
            "You can send that first call again from the reminder in FollowThrough Health."
        )
    if reminder.call_status == "stopped":
        return "No reminder call was made, because reminder calls were turned off from the phone (someone pressed 9)."
    return "Nobody marked it as taken in FollowThrough Health."


def alert_missed(db: Session, event: ReminderEvent, reminder: MedicineReminder) -> None:
    if not reminder.alert_on_miss or not settings.email_delivery_enabled or event.alerted_at:
        return
    owner = db.get(User, reminder.user_id)
    if owner is None:
        return
    person = decrypt_field(reminder.encrypted_person) or "your family member"
    clock = friendly_clock(as_utc(event.due_at).astimezone(zone(reminder.timezone)))
    message = base_message(owner.email, f"FollowThrough Health: the {clock} medicine reminder for {person} was not confirmed")
    # Never include the reminder label: families sometimes type the medicine name there.
    message.set_content(
        f"Hello,\n\nThe {clock} medicine reminder for {person} was not confirmed today.\n\n"
        f"{why_not_confirmed(event, reminder, person)}\n\n"
        "What you can do:\n"
        f"- Check in with {person}.\n"
        "- If it was taken, open FollowThrough Health and tap Taken on that reminder.\n\n"
        "This is a reminder service, not a medical alert. "
        "In an emergency, call your local emergency number.\n\n"
        f"Manage reminders: {settings.frontend_url}\n\nFollowThrough Health"
    )
    try:
        send_email(message)
        event.alerted_at = datetime.now(timezone.utc)
    except Exception:  # noqa: BLE001
        log.exception("Missed-reminder email failed for %s", event.id)


def run_dispatch(db: Session, now: datetime) -> dict:
    counts = {"created": 0, "calls": 0, "call_failures": 0, "missed": 0}
    calls_on = settings.reminder_calls_enabled
    for reminder in db.scalars(select(MedicineReminder).where(MedicineReminder.active == 1)).all():
        local_now = now.astimezone(zone(reminder.timezone))
        for local_day in {local_now.date(), (local_now - DUE_WINDOW).date()}:
            for _clock, due_at in due_moments(reminder, local_day):
                if now - DUE_WINDOW < due_at <= now and not find_event(db, reminder.id, "dose", due_at):
                    new_event(db, reminder, "dose", due_at)
                    counts["created"] += 1
    open_events = db.scalars(
        select(ReminderEvent).where(
            ReminderEvent.status.in_(("due", "calling")), ReminderEvent.due_at > now - timedelta(days=1)
        )
    ).all()
    for event in open_events:
        reminder = db.get(MedicineReminder, event.reminder_id)
        if reminder is None or not reminder.active:
            continue
        calling = calls_on and (
            (event.kind == "consent" and reminder.call_status == "pending_consent")
            or (event.kind == "dose" and reminder.call_status == "active")
        )
        last_call = as_utc(event.last_call_at) if event.last_call_at else None
        if calling and event.attempts == 0:
            counts["calls"] += 1
            counts["call_failures"] += not call_for(event, reminder)
        elif calling and event.attempts == 1 and last_call and last_call <= now - RETRY_AFTER:
            counts["calls"] += 1
            counts["call_failures"] += not call_for(event, reminder)
        elif calling and event.attempts >= 2 and last_call and last_call <= now - GIVE_UP_AFTER:
            event.status = "missed"
            counts["missed"] += 1
            if event.kind == "dose":
                alert_missed(db, event, reminder)
        elif not calling and event.kind == "dose" and as_utc(event.due_at) <= now - APP_ONLY_MISSED_AFTER:
            event.status = "missed"
            counts["missed"] += 1
            alert_missed(db, event, reminder)
    db.commit()
    return counts


@router.post("/dispatch", dependencies=[Depends(require_cron_token)])
def dispatch(db: Session = Depends(get_db)):
    return run_dispatch(db, datetime.now(timezone.utc))


STUCK_AFTER = timedelta(hours=2)


def reminder_health(db: Session, now: datetime) -> dict:
    # Counts only, never names or numbers. A reminder still "due" or "calling" two hours
    # after its time means the 5-minute scheduler is not running or is failing.
    week_ago = now - timedelta(days=7)
    open_states = ("due", "calling")
    stuck = db.scalar(
        select(func.count(ReminderEvent.id)).where(
            ReminderEvent.status.in_(open_states),
            ReminderEvent.due_at <= now - STUCK_AFTER,
            ReminderEvent.due_at > week_ago,
        )
    )
    missed = db.scalar(
        select(func.count(ReminderEvent.id)).where(
            ReminderEvent.status == "missed", ReminderEvent.due_at > now - timedelta(days=1)
        )
    )
    return {"healthy": not stuck, "stuck_events": stuck or 0, "missed_last_24h": missed or 0}


@router.get("/health", dependencies=[Depends(require_cron_token)])
def health(db: Session = Depends(get_db)):
    return reminder_health(db, datetime.now(timezone.utc))


# --- Twilio voice webhooks -----------------------------------------------------


async def twilio_params(request: Request) -> dict[str, str]:
    params = dict(urllib.parse.parse_qsl((await request.body()).decode()))
    url = reminder_calls.public_url(request.url.path)
    if not reminder_calls.valid_twilio_signature(url, params, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed.")
    return params


def xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


def event_for_token(db: Session, token: str) -> tuple[ReminderEvent | None, MedicineReminder | None]:
    event = db.scalar(select(ReminderEvent).where(ReminderEvent.token_hash == token_hash(token)))
    reminder = db.get(MedicineReminder, event.reminder_id) if event else None
    return event, reminder


def ask(reminder: MedicineReminder, event: ReminderEvent, token: str) -> Response:
    caller = decrypt_field(reminder.encrypted_caller_name) if reminder.encrypted_caller_name else ""
    text = reminder_calls.script(reminder.language, event.kind, caller)
    return xml(reminder_calls.gather_twiml(reminder.language, text, reminder_calls.public_url(f"/reminders/voice/{token}/answer")))


@router.post("/voice/{token}")
async def voice_start(token: str, request: Request, db: Session = Depends(get_db)):
    await twilio_params(request)
    event, reminder = event_for_token(db, token)
    if event is None or reminder is None or not reminder.active or reminder.call_status in ("off", "stopped"):
        return xml(reminder_calls.goodbye_twiml("en", reminder_calls.script("en", "unknown")))
    return ask(reminder, event, token)


@router.post("/voice/{token}/answer")
async def voice_answer(token: str, request: Request, db: Session = Depends(get_db)):
    params = await twilio_params(request)
    event, reminder = event_for_token(db, token)
    if event is None or reminder is None:
        return xml(reminder_calls.goodbye_twiml("en", reminder_calls.script("en", "unknown")))
    language = reminder.language
    caller = decrypt_field(reminder.encrypted_caller_name) if reminder.encrypted_caller_name else ""
    digit = params.get("Digits", "")
    now = datetime.now(timezone.utc)
    if digit == "9":
        reminder.call_status = "stopped"
        event.status = "stopped"
        db.commit()
        return xml(reminder_calls.goodbye_twiml(language, reminder_calls.script(language, "stopped")))
    if digit == "1" and event.kind == "consent":
        reminder.call_status = "active"
        reminder.consent_at = now
        event.status = "taken"
        event.confirmed_at = now
        db.commit()
        return xml(reminder_calls.goodbye_twiml(language, reminder_calls.script(language, "consent_yes")))
    if digit == "1":
        event.status = "taken"
        event.confirmed_at = now
        db.commit()
        return xml(reminder_calls.goodbye_twiml(language, reminder_calls.script(language, "taken", caller)))
    return ask(reminder, event, token)
