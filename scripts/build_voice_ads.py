"""Build the ad voiceover package from docs/voice-ads/campaigns.json.

Writes one script sheet per campaign (<id>.md) and one subtitle file per version and language
(<id>-<seconds>s-<lang>.srt), so captions always match the spoken words and timing.
Usage: python scripts/build_voice_ads.py [--check]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs" / "voice-ads"
GAP = 0.2  # breath between lines, in seconds
LANGS = {"en": "English", "es": "Spanish (DRAFT for a qualified language reviewer)"}

MIXING = [
    "Voice recorded or generated at 48 kHz, 24-bit, in a quiet room; no clipping (peaks at or below -1 dBTP).",
    "Final mix about -14 LUFS integrated for social video (YouTube, Instagram, TikTok, Facebook).",
    "Music 15 to 20 dB under the voice while anyone speaks; no music over the disclaimer card.",
    "No sound effects that sound like a phone alarm, siren or heart monitor.",
    "Captions burned in or uploaded as the .srt here; they must match the spoken words exactly.",
    "Check on a phone speaker at low volume and on earbuds before approval.",
]
DISCLOSURES = [
    "Label any AI-generated voice as AI-generated where the platform asks (Meta, TikTok and YouTube "
    "have AI-content labels).",
    "Use a voice actor's own voice or a stock synthetic voice with a commercial licence. "
    "Never clone a real person's voice.",
    "No testimonials, patient stories presented as real, doctor endorsements or result claims.",
    "Health-related ads may need platform review or special-category settings; the founder "
    "checks each platform's health ad policy before buying.",
]


def timestamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def cues(lines: list) -> list[tuple[float, float, str]]:
    out, start = [], 0.0
    for duration, text in lines:
        out.append((start, start + duration, text))
        start += duration + GAP
    return out


def srt(lines: list) -> str:
    blocks = [
        f"{i}\n{timestamp(a)} --> {timestamp(b)}\n{text}\n"
        for i, (a, b, text) in enumerate(cues(lines), 1)
    ]
    return "\n".join(blocks)


def sheet(c: dict) -> str:
    out = [
        f"# {c['title']}",
        "",
        "Status: **draft for approval**. Not published. Spanish is a draft for a qualified "
        "language reviewer.",
        "",
        f"- **Audience:** {c['audience']}",
        f"- **Style:** {c['style']}",
        f"- **Voice:** {c['voice']}",
        f"- **Visuals:** {c['visuals']}",
        f"- **Music:** {c['music']}",
        "- **On screen (not spoken):** " + " / ".join(c["on_screen"]),
        "",
    ]
    for length in ("30", "15"):
        for lang, name in LANGS.items():
            lines = c["versions"][length][lang]
            out += [f"## {length}-second version, {name}", "", "| Time | Voiceover |", "|---|---|"]
            out += [f"| {a:.1f}–{b:.1f}s | {text} |" for a, b, text in cues(lines)]
            out += [
                "",
                f"Subtitles: [`{c['id']}-{length}s-{lang}.srt`]({c['id']}-{length}s-{lang}.srt). "
                "Pacing: a short breath between lines; end card holds the last line.",
                "",
            ]
    out += ["## Audio mixing", ""] + [f"- {m}" for m in MIXING]
    out += ["", "## Required disclosures", ""] + [f"- {d}" for d in DISCLOSURES] + [""]
    return "\n".join(out)


def build() -> dict[Path, str]:
    data = json.loads((ROOT / "campaigns.json").read_text())
    files = {}
    for c in data["campaigns"]:
        files[ROOT / f"{c['id']}.md"] = sheet(c)
        for length, langs in c["versions"].items():
            for lang, lines in langs.items():
                files[ROOT / f"{c['id']}-{length}s-{lang}.srt"] = srt(lines)
    return files


def main() -> int:
    files = build()
    if "--check" in sys.argv:
        stale = [p.name for p, text in files.items() if not p.exists() or p.read_text() != text]
        if stale:
            print("Out of date, run python scripts/build_voice_ads.py:", ", ".join(stale))
            return 1
        return 0
    for path, text in files.items():
        path.write_text(text)
    print(f"Wrote {len(files)} files to {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
