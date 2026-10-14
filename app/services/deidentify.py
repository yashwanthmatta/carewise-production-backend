import re

# Removes direct identifiers from text before any export or training use, following the
# HIPAA Safe Harbor list where it applies to lab letters: names we know, contact details,
# record numbers, street addresses and full dates (only the year is kept). Test names,
# values, units, ranges and flags are kept because they are the signal. This is a first
# pass, not a guarantee: rare conditions with exact values can still point to a person,
# so a person reviews the first export of every clinic by hand.

REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[URL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b(?:MRN|medical record(?: number| no\.?| #)?|patient id|account(?: number| no\.?| #)?|acct|accession(?: number| no\.?| #)?)\s*[:#]?\s*[A-Z0-9-]{3,}", re.I), "[ID]"),
    (re.compile(r"\b(?:DOB|date of birth|birth ?date|born)\b\s*[:]?\s*[^\n,;]{0,30}", re.I), "[DOB]"),
    (re.compile(r"^\s*(?:patient(?: name)?|name)\s*:.*$", re.I | re.M), "[NAME LINE]"),
    (re.compile(r"^\s*(?:address|addr|city|home)\s*:.*$", re.I | re.M), "[ADDRESS LINE]"),
    (re.compile(r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl|Terrace|Circle|Parkway|Pkwy)\b\.?"), "[ADDRESS]"),
    (re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"), "[STATE ZIP]"),
    (re.compile(r"\b((?i:hi|hello|dear|hey)\s+)(?!(?i:patient|there|team|all)\b)(?:(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?"), r"\1[NAME]"),
]

MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATES = [
    re.compile(r"\b((?:19|20)\d{2})-\d{1,2}-\d{1,2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/((?:19|20)\d{2})\b"),
    re.compile(rf"\b{MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})\b", re.I),
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\.?,?\s+((?:19|20)\d{{2}})\b", re.I),
]
SHORT_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2}\b")
OLD_AGE = re.compile(r"\b(9\d|1[01]\d)[\s-]*(?:years?|yrs?|y/?o)\b(?:[\s-]*old)?", re.I)


def deidentify_text(text: str, known: list[str] | tuple[str, ...] = ()) -> str:
    """Replace identifiers with placeholders. `known` lists exact strings to remove, such as
    the patient reference, clinician and clinic names."""
    out = text or ""
    for value in sorted({k.strip() for k in known if k and len(k.strip()) >= 2}, key=len, reverse=True):
        out = re.sub(re.escape(value), "[REDACTED]", out, flags=re.I)
    for pattern, replacement in REDACTIONS:
        out = pattern.sub(replacement, out)
    for pattern in DATES:
        out = pattern.sub(lambda m: m.group(1), out)
    out = SHORT_DATE.sub("[DATE]", out)
    return OLD_AGE.sub("90+ years", out)


def year_only(date_text: str) -> str:
    match = re.match(r"((?:19|20)\d{2})", date_text or "")
    return match.group(1) if match else ""
