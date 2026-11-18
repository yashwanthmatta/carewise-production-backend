"""Medicine reference: names people type, matched to entries whose facts were checked against a cited source.

Only entries with review_status "source-verified" are ever used (sent to the model as context, or
returned as sources). Entries still waiting for their source check carry names only and are skipped,
so nothing unverified reaches an answer. See docs/medical-knowledge-system.md.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "medicine_reference.json"
VERIFIED = "source-verified"
_REQUIRED_WHEN_VERIFIED = ("summary", "sources", "active_ingredients")


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


@lru_cache(maxsize=1)
def load_reference() -> dict:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    for entry in data.get("entries", []):
        if entry.get("review_status") == VERIFIED:
            missing = [key for key in _REQUIRED_WHEN_VERIFIED if not entry.get(key)]
            if missing or not all(source.get("url") and source.get("checked") for source in entry["sources"]):
                raise ValueError(f"medicine reference entry {entry.get('id')} is marked verified but lacks {missing or 'source dates'}")
    return data


def find_mentions(text: str, verified_only: bool = True) -> list[dict]:
    """Entries whose name or alias appears in the text as whole words ("dolo650" also matches "dolo 650")."""
    spaced = f" {_norm(text)} "
    compact = spaced.replace(" ", "")
    found = []
    for entry in load_reference().get("entries", []):
        if verified_only and entry.get("review_status") != VERIFIED:
            continue
        for name in [entry["name"], *entry.get("aliases", [])]:
            key = _norm(name)
            if not key:
                continue
            # Names with a number ("Dolo 650") may be typed without a space; plain words need whole-word matches.
            if f" {key} " in spaced or (any(ch.isdigit() for ch in key) and key.replace(" ", "") in compact):
                found.append(entry)
                break
    return found


def context_for(text: str) -> str:
    lines = []
    for entry in find_mentions(text):
        ingredients = ", ".join(f"{item['name']} {item.get('strength', '')}".strip() for item in entry["active_ingredients"])
        market = f" ({entry['market']})" if entry.get("market") else ""
        sources = "; ".join(f"{source['title']}, read {source['checked']}" for source in entry["sources"])
        lines.append(f"- {entry['name']}{market}: {ingredients}. {entry['summary']} Source: {sources}.")
    return "\n".join(lines)


def sources_for(text: str) -> list[dict]:
    seen, out = set(), []
    for entry in find_mentions(text):
        for source in entry["sources"]:
            if source["url"] not in seen:
                seen.add(source["url"])
                out.append({"title": source["title"], "url": source["url"]})
    return out
