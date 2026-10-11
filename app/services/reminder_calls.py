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

SCRIPTS = {
    "en": {
        "consent": "Hello. This is CareWise. {caller} set up phone calls to remind you when it is time for your medicine. "
        "To agree to these reminder calls, press 1. If you do not want them, press 9.",
        "dose": "Hello, this is CareWise, with a reminder from {caller}. It is time for your medicine. "
        "If you have taken it, press 1. To hear this again, press 2. To stop these calls, press 9.",
        "consent_yes": "Thank you. You will get a call at each reminder time. Goodbye.",
        "taken": "Thank you. We will let {caller} know. Goodbye.",
        "stopped": "These reminder calls are now turned off. Goodbye.",
        "no_answer": "We did not hear an answer. Goodbye.",
        "unknown": "This reminder is no longer active. Goodbye.",
        "family": "your family",
    },
    "es": {
        "consent": "Hola. Le llama CareWise. {caller} programó llamadas para recordarle cuándo tomar su medicina. "
        "Para aceptar estas llamadas, marque 1. Si no las desea, marque 9.",
        "dose": "Hola, le llama CareWise con un recordatorio de {caller}. Es hora de tomar su medicina. "
        "Si ya la tomó, marque 1. Para escuchar de nuevo, marque 2. Para dejar de recibir estas llamadas, marque 9.",
        "consent_yes": "Gracias. Recibirá una llamada a cada hora del recordatorio. Adiós.",
        "taken": "Gracias. Se lo diremos a {caller}. Adiós.",
        "stopped": "Las llamadas de recordatorio están desactivadas. Adiós.",
        "no_answer": "No escuchamos una respuesta. Adiós.",
        "unknown": "Este recordatorio ya no está activo. Adiós.",
        "family": "su familia",
    },
}


def script(language: str, key: str, caller: str = "") -> str:
    lines = SCRIPTS.get(language, SCRIPTS["en"])
    return lines[key].format(caller=caller.strip() or lines["family"])


def say(language: str, text: str) -> str:
    voice, lang = VOICES.get(language, VOICES["en"])
    return f'<Say voice="{voice}" language="{lang}">{escape(text)}</Say>'


def twiml(*parts: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def gather_twiml(language: str, text: str, action_url: str) -> str:
    # Ask once, ask again if there is no keypress, then hang up politely.
    prompt = f'<Gather numDigits="1" timeout="8" method="POST" action="{escape(action_url)}">{say(language, text)}</Gather>'
    return twiml(prompt, prompt, say(language, script(language, "no_answer")), "<Hangup/>")


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
