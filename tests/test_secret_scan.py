"""The secret scan catches credential-shaped strings and never prints them.

Test strings are assembled at run time so this file itself contains no matching literal."""

from scripts.security import secret_scan


def fake(prefix: str, body: str) -> str:
    return prefix + body


def test_finds_credential_shapes():
    samples = {
        "AWS access key": fake("AK" + "IA", "A" * 16),
        "Anthropic API key": fake("sk-" + "ant-", "x" * 30),
        "Stripe live key": fake("sk_" + "live_", "9" * 24),
        "GitHub token": fake("gh" + "p_", "a" * 36),
        "Private key": "-----BEGIN " + "PRIVATE KEY-----",
    }
    for name, value in samples.items():
        assert secret_scan.scan_text(f"line one\nvalue = '{value}'\n") == [(2, name)], name


def test_ignores_ordinary_text_and_settings_names():
    text = "CAREWISE_STRIPE_SECRET_KEY = settings.stripe_secret_key\nsk_test_placeholder\nAKIA is a prefix\n"
    assert secret_scan.scan_text(text) == []


def test_repository_is_clean(capsys):
    assert secret_scan.main() == 0
    assert "No credential-shaped strings" in capsys.readouterr().out
