"""Encrypt plaintext health fields and move encrypted fields to the current key.

Report only (default, changes nothing):
    PYTHONPATH=. python scripts/security/encrypt_fields.py
Rewrite, resumable:
    PYTHONPATH=. python scripts/security/encrypt_fields.py --apply --checkpoint /tmp/encrypt-fields.json

Prints counts and key ids only, never a stored value or a key.
See docs/security-hardening/encryption-migration.md before running against production.
"""

import argparse
import json
import sys
from pathlib import Path

from app.db.session import engine
from app.services.field_encryption_migration import run, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Rewrite values (default is a report that changes nothing).")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--checkpoint", type=Path, help="Progress file, so an interrupted run continues.")
    parser.add_argument("--table", action="append", help="Limit to this table (repeatable).")
    parser.add_argument(
        "--to-plaintext",
        action="store_true",
        help="Rollback only: write plaintext back into the newly encrypted columns before releasing an older backend. Needs --apply and --i-understand.",
    )
    parser.add_argument("--i-understand", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.to_plaintext and not (args.apply and args.i_understand):
        parser.error("--to-plaintext stores health data unencrypted again; it needs --apply and --i-understand.")

    results = run(
        engine,
        apply=args.apply,
        batch_size=args.batch_size,
        checkpoint_path=args.checkpoint,
        only_tables=set(args.table or []) or None,
        to_plaintext=args.to_plaintext,
    )
    output = summary(results)
    output["mode"] = "to_plaintext" if args.to_plaintext else ("apply" if args.apply else "report")
    print(json.dumps(output, indent=2, sort_keys=True))
    unreadable = sum(column["unreadable"] for table in output["tables"].values() for column in table.values())
    return 1 if unreadable else 0


if __name__ == "__main__":
    sys.exit(main())
