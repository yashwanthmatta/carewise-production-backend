# Disclosures from the legal and advertising review (carewise-frontend
# docs/legal-advertising-review.md, LA-03 and LA-08). Not legal advice; wording pending counsel.
from app.api.routes.subscriptions import SUBSCRIPTION_PLANS, checkout_session_data, renewal_notice
from app.core.config import settings
from app.services import reminder_calls


def test_callback_number_said_on_consent_and_dose_calls(monkeypatch):
    monkeypatch.setattr(settings, "reminder_callback_number", "+1 (555) 010-2030")
    for language, phrase in (("en", "To reach FollowThrough Health, call"), ("es", "llame al")):
        for key in ("consent", "dose"):
            text = reminder_calls.script(language, key, "Maria")
            assert phrase in text
            assert text.endswith("1, 5 5 5, 0 1 0, 2 0 3 0.")


def test_no_callback_line_when_number_not_set(monkeypatch):
    monkeypatch.setattr(settings, "reminder_callback_number", "")
    for key in ("consent", "dose"):
        assert "To reach" not in reminder_calls.script("en", key, "Maria")
        assert "llame al" not in reminder_calls.script("es", key, "Maria")


def test_callback_line_only_on_consent_and_dose(monkeypatch):
    monkeypatch.setattr(settings, "reminder_callback_number", "5550102030")
    for key in ("consent_yes", "taken", "stopped", "no_answer", "unknown"):
        assert "To reach FollowThrough Health" not in reminder_calls.script("en", key, "Maria")


def test_callback_line_never_names_a_medicine(monkeypatch):
    monkeypatch.setattr(settings, "reminder_callback_number", "5550102030")
    text = reminder_calls.script("en", "dose", "Maria")
    assert "mg" not in text and "dose of" not in text


def test_spoken_number_groups_digits():
    assert reminder_calls.spoken_number("5550102030") == "5 5 5, 0 1 0, 2 0 3 0"
    assert reminder_calls.spoken_number("") == ""


def test_checkout_shows_auto_renewal_and_cancel_terms():
    for code in ("plus", "premium"):
        plan = SUBSCRIPTION_PLANS[code]
        data = checkout_session_data(plan, "sub_1", "family@example.com")
        assert data["mode"] == "subscription"
        assert data["line_items[0][price_data][recurring][interval]"] == "month"
        message = data["custom_text[submit][message]"]
        assert message == renewal_notice(plan)
        assert "renews automatically every month" in message
        assert f"${int(plan['monthly_price_usd'])}" in message
        assert "until you cancel" in message and "Manage or cancel plan" in message
        assert len(message) <= 1200  # Stripe's limit for custom text
