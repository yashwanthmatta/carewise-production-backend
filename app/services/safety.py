import re

EMERGENCY_TERMS = [
    "chest pain",
    "trouble breathing",
    "shortness of breath",
    "stroke",
    "suicide",
    "severe bleeding",
    "fainting",
    "confusion",
    "face droop",
    "slurred speech",
    "arm weakness",
    "seizure",
    "loss of consciousness",
    "overdose",
    "poison",
    "anaphylaxis",
]

CONDITION_TERMS = {
    "diabetes": ["diabetes", "glucose", "blood sugar", "a1c"],
    "hypertension": ["hypertension", "blood pressure", "bp"],
    "heart_support": ["heart", "cholesterol"],
    "kidney_support": ["kidney", "ckd", "renal"],
    "mental_health": ["anxiety", "depression", "stress", "insomnia", "sleep"],
}


def is_negated(text: str, index: int) -> bool:
    window = text[max(0, index - 24):index]
    after = text[index:index + 48]
    if "after stroke" in f"{window}{after}" or "recovery" in after:
        return True
    return any(pattern in window for pattern in ["no ", "not ", "without ", "denies "])


def emergency_flags(text: str) -> list[str]:
    lowered = text.lower()
    flags = []
    for term in EMERGENCY_TERMS:
        index = lowered.find(term)
        if index >= 0 and not is_negated(lowered, index):
            flags.append(term)
    if re.search(r"\b(1[8-9]\d|[2-9]\d{2})\s*(?:/|over)\s*(1[2-9]\d|[2-9]\d{2})\b", lowered):
        flags.append("blood pressure over 180/120")
    return flags


def matched_conditions(text: str) -> list[str]:
    lowered = text.lower()
    matches = [name for name, terms in CONDITION_TERMS.items() if any(term in lowered for term in terms)]
    return matches or ["general_support"]


def requires_clinician_review(flags: list[str], conditions: list[str]) -> bool:
    high_risk = {"heart_support", "kidney_support"}
    return bool(flags) or any(condition in high_risk for condition in conditions)
