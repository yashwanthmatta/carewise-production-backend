import base64
import hashlib
import hmac
import json
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

from app.core.config import settings

# Phone-call reminders through Twilio's REST API and TwiML. The call always uses a
# fixed script: it never says medicine names, doses or health advice, so whoever
# answers hears only that it is time for the medicine they planned with family.

VOICES = {"en": ("Polly.Joanna", "en-US"), "es": ("Polly.Lupe", "es-US")}

# Written for an older listener: short sentences, who is calling first, the action before
# the key, and how to stop. The Spanish lines are a draft waiting for review by a native speaker.
SCRIPTS = {
    "en": {
        "consent": "Hello. This is an automated call from FollowThrough Health. "
        "{caller} asked us to call you when it is time for your medicine. Is that okay? "
        "To say yes, press 1. To say no, press 9. To hear this again, press 2.",
        "dose": "Hello. This is FollowThrough Health, with a reminder from {caller}. It is time for your medicine. "
        "If you have taken it, press 1. To hear this again, press 2. To stop these calls, press 9.",
        "consent_yes": "Thank you. We will call you at each reminder time. "
        "To stop the calls, press 9 during any call. Goodbye.",
        "taken": "Thank you. We will let {caller} know. Goodbye.",
        "stopped": "Okay. These reminder calls are now turned off. You will not get any more calls. Goodbye.",
        "no_answer": "We did not hear a button press. Goodbye for now.",
        "unknown": "This reminder is no longer active. Goodbye.",
        "family": "your family",
    },
    "es": {
        "consent": "Hola. Esta es una llamada automática de FollowThrough Health. "
        "{caller} nos pidió que le llamemos cuando sea hora de tomar su medicina. ¿Está de acuerdo? "
        "Para decir que sí, marque 1. Para decir que no, marque 9. Para escuchar este mensaje otra vez, marque 2.",
        "dose": "Hola. Le llama FollowThrough Health con un recordatorio de {caller}. Es hora de tomar su medicina. "
        "Si ya la tomó, marque 1. Para escuchar este mensaje otra vez, marque 2. Para dejar de recibir estas llamadas, marque 9.",
        "consent_yes": "Gracias. Le llamaremos cada vez que sea hora de su recordatorio. "
        "Si quiere dejar de recibirlas, marque 9 durante cualquier llamada. Adiós.",
        "taken": "Gracias. Se lo diremos a {caller}. Adiós.",
        "stopped": "Muy bien. Las llamadas de recordatorio están desactivadas. No recibirá más llamadas. Adiós.",
        "no_answer": "No recibimos ninguna respuesta. Adiós por ahora.",
        "unknown": "Este recordatorio ya no está activo. Adiós.",
        "family": "su familia",
    },
}

# Polly voices read SSML inside <Say>; a slightly slower rate is easier to follow on a phone.
SPEAKING_RATE = "90%"


def script(language: str, key: str, caller: str = "") -> str:
    lines = SCRIPTS.get(language, SCRIPTS["en"])
    return lines[key].format(caller=caller.strip() or lines["family"])


def say(language: str, text: str) -> str:
    voice, lang = VOICES.get(language, VOICES["en"])
    return f'<Say voice="{voice}" language="{lang}"><prosody rate="{SPEAKING_RATE}">{escape(text)}</prosody></Say>'


def twiml(*parts: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def gather_twiml(language: str, text: str, action_url: str) -> str:
    # A short pause lets the person settle after "hello?". Ask once, ask again if there is
    # no keypress (with time to find the keypad), then hang up politely.
    prompt = f'<Gather numDigits="1" timeout="10" method="POST" action="{escape(action_url)}">{say(language, text)}</Gather>'
    return twiml('<Pause length="1"/>', prompt, prompt, say(language, script(language, "no_answer")), "<Hangup/>")


def goodbye_twiml(language: str, text: str) -> str:
    return twiml(say(language, text), "<Hangup/>")


def public_url(path: str) -> str:
    return settings.clean_env_value(settings.public_api_url).rstrip("/") + path


def valid_twilio_signature(url: str, params: dict[str, str], signature: str) -> bool:
    # https://www.twilio.com/docs/usage/security#validating-requests
    token = settings.clean_env_value(settings.twilio_auth_token)
    if not token or not signature:
        return False
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(digest, signature)


def place_call(to_number: str, voice_url: str) -> str:
    """Start an outbound call; Twilio then fetches voice_url for what to say."""
    sid = settings.clean_env_value(settings.twilio_account_sid)
    body = urllib.parse.urlencode(
        {
            "To": to_number,
            "From": settings.clean_env_value(settings.twilio_from_number),
            "Url": voice_url,
            "Method": "POST",
            "Timeout": "25",
        }
    ).encode()
    request = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(sid)}/Calls.json", data=body, method="POST"
    )
    credentials = base64.b64encode(f"{sid}:{settings.clean_env_value(settings.twilio_auth_token)}".encode()).decode()
    request.add_header("Authorization", f"Basic {credentials}")
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode()).get("sid", "")
