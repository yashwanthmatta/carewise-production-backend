"""Fail if a tracked file contains something shaped like a live credential.

Prints the file, line and kind of match only, never the matched text, so CI logs stay
clean. Run: python scripts/security/secret_scan.py  (exit 1 when anything is found).
"""

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "Anthropic API key": r"sk-ant-[A-Za-z0-9_-]{20,}",
    "OpenAI API key": r"sk-(?:proj-)?[A-Za-z0-9]{32,}",
    "Stripe live key": r"(?:sk|rk)_live_[0-9a-zA-Z]{20,}",
    "Stripe webhook secret": r"whsec_[0-9a-zA-Z]{20,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}",
    "Slack token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "SendGrid key": r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}",
    "Private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}
COMPILED = {name: re.compile(pattern) for name, pattern in PATTERNS.items()}
SKIP_PARTS = {"node_modules", "vendor", ".git"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".wasm", ".gz", ".zip"}


def scan_text(text: str) -> list[tuple[int, str]]:
    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in COMPILED.items():
            if pattern.search(line):
                hits.append((number, name))
    return hits


def tracked_files(root: Path) -> list[Path]:
    output = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
    files = []
    for name in output.splitlines():
        path = Path(name)
        if SKIP_PARTS & set(path.parts) or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(root / path)
    return files


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    found = 0
    for path in tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, name in scan_text(text):
            found += 1
            print(f"{path.relative_to(root)}:{number}: looks like a {name} (value not shown)")
    if found:
        print(f"{found} possible secret(s). Remove them, rotate the credential, and keep secrets in Render settings.")
        return 1
    print("No credential-shaped strings found in tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
