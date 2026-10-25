import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADS = ROOT / "docs" / "voice-ads"
DATA = json.loads((ADS / "campaigns.json").read_text())
VERSIONS = [
    (c, length, lang, lines)
    for c in DATA["campaigns"]
    for length, langs in c["versions"].items()
    for lang, lines in langs.items()
]
IDS = [f"{c['id']}-{length}s-{lang}" for c, length, lang, _ in VERSIONS]

# Claims we must never make in an ad (see the agent rules and the website's own wording).
BANNED = [
    r"hipaa", r"clinically (validated|proven)", r"\baccura", r"guarantee", r"diagnoses\b",
    r"\bcures?\b", r"\bdr\.", r"doctor[- ]approved", r"recommended by", r"trusted by",
    r"\d+\s*(%|percent|families|users|doctors)", r"\bmg\b", r"\bpills?\b", r"\btablets?\b",
    r"dosis", r"\bdose\b", r"pastilla", r"garantiza", r"precis",
]


def test_generated_files_match_the_source():
    result = subprocess.run(
        [sys.executable, "scripts/build_voice_ads.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(("campaign", "length", "lang", "lines"), VERSIONS, ids=IDS)
def test_voiceover_fits_and_reads_slowly(campaign, length, lang, lines):
    total = sum(duration for duration, _ in lines) + 0.2 * (len(lines) - 1)
    assert total <= int(length), f"{total:.1f}s is longer than {length}s"
    assert total >= int(length) - 3, "leaves too much silence"
    for duration, text in lines:
        words = len(text.split())
        assert words / duration <= 3.0, f"too fast to say clearly: {text!r}"
        assert len(text) / duration <= 20, f"caption too fast to read: {text!r}"
        for pattern in BANNED:
            assert not re.search(pattern, text, re.IGNORECASE), f"{pattern!r} in {text!r}"
    brand = "DocBridge" if campaign["id"] == "docbridge" else "FollowThrough Health"
    assert any(brand in text for _, text in lines)


@pytest.mark.parametrize("campaign", DATA["campaigns"], ids=[c["id"] for c in DATA["campaigns"]])
def test_spanish_matches_english_and_disclosures_are_on_screen(campaign):
    for length, langs in campaign["versions"].items():
        assert len(langs["en"]) == len(langs["es"]), f"{length}s cue count differs"
        assert [d for d, _ in langs["en"]] == [d for d, _ in langs["es"]], "timings differ"
    on_screen = " ".join(campaign["on_screen"]).lower()
    assert "synthetic" in on_screen
    assert "medical advice" in on_screen or "diagnose" in on_screen


def test_subtitles_match_spoken_words_exactly():
    for c, length, lang, lines in VERSIONS:
        srt = (ADS / f"{c['id']}-{length}s-{lang}.srt").read_text()
        spoken = [text for _, text in lines]
        captions = [block.split("\n", 2)[2].strip() for block in srt.strip().split("\n\n")]
        assert captions == spoken
        times = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3})", srt)
        seconds = [int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in times]
        assert seconds == sorted(seconds) and seconds[-1] <= int(length)
