"""Encrypt existing plaintext health fields and move encrypted fields to the current key.

One tool does both jobs, because both mean "make every stored value a token under the current
key": plaintext left from before a column was encrypted, bare Fernet tokens from before key ids,
and tokens under an older key id are all rewritten; values already under the current key are
skipped, so running it twice changes nothing.

Safety rules:
- Values are read and written as raw strings (not through EncryptedText), so the tool sees
  exactly what is stored.
- Every new value is decrypted again and compared before it is written; a mismatch stops the run.
- Nothing about a value is printed or logged except counts and key ids.
- Progress is saved per table after every batch, so an interrupted run continues where it stopped.
- A value that cannot be decrypted is counted and left untouched, never replaced.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.core.crypto import EncryptedText, FieldDecryptionError, current_key_id, decrypt_field, encrypt_field, key_id_of
from app.db.base import Base


@dataclass(frozen=True)
class EncryptedColumn:
    table: str
    column: str
    primary_key: str
    typed: bool  # True: EncryptedText column (may still hold plaintext); False: encrypted_* column


def encrypted_columns() -> list[EncryptedColumn]:
    from app.models import carewise  # noqa: F401  (registers every table)

    found = []
    for table in Base.metadata.sorted_tables:
        primary_key = [column.name for column in table.primary_key.columns]
        if len(primary_key) != 1:
            continue
        for column in table.columns:
            typed = isinstance(column.type, EncryptedText)
            if typed or column.name.startswith("encrypted_"):
                found.append(EncryptedColumn(table.name, column.name, primary_key[0], typed))
    return found


@dataclass
class ColumnReport:
    counts: dict[str, int] = field(default_factory=dict)
    rewritten: int = 0
    unreadable: int = 0


def _raw_table(spec: EncryptedColumn) -> sa.TableClause:
    return sa.table(spec.table, sa.column(spec.primary_key, sa.String), sa.column(spec.column, sa.Text))


def _needs_rewrite(value: str, current: str) -> bool:
    kind = key_id_of(value)
    return kind not in ("empty", current)


def run(
    engine: Engine,
    *,
    apply: bool = False,
    batch_size: int = 200,
    checkpoint_path: Path | None = None,
    only_tables: set[str] | None = None,
    to_plaintext: bool = False,
) -> dict[str, dict[str, ColumnReport]]:
    """Count (and with apply=True, rewrite) stored values per table and column.

    to_plaintext=True is the rollback path for releasing an older backend that predates
    EncryptedText: it writes plaintext back into EncryptedText columns only (encrypted_* columns
    stay encrypted, because every release reads those).

    Returns {table: {column: ColumnReport}}. Counts are by key id, with "plaintext", "legacy"
    and "empty" for values that have none.
    """
    current = current_key_id()
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path and checkpoint_path.exists() else {}
    by_table: dict[str, list[EncryptedColumn]] = {}
    for spec in encrypted_columns():
        if only_tables and spec.table not in only_tables:
            continue
        by_table.setdefault(spec.table, []).append(spec)

    results: dict[str, dict[str, ColumnReport]] = {}
    inspector = sa.inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table_name, specs in by_table.items():
        if table_name not in existing_tables:
            continue
        reports = {spec.column: ColumnReport() for spec in specs}
        results[table_name] = reports
        primary_key = specs[0].primary_key
        table = sa.table(table_name, sa.column(primary_key, sa.String), *[sa.column(spec.column, sa.Text) for spec in specs])
        last_id = checkpoint.get(table_name, "") if apply else ""
        while True:
            with engine.begin() as connection:
                query = sa.select(table).order_by(table.c[primary_key]).limit(batch_size)
                if last_id:
                    query = query.where(table.c[primary_key] > last_id)
                rows = connection.execute(query).mappings().all()
                if not rows:
                    break
                for row in rows:
                    updates = {}
                    for spec in specs:
                        value = row[spec.column] or ""
                        report = reports[spec.column]
                        kind = key_id_of(value)
                        report.counts[kind] = report.counts.get(kind, 0) + 1
                        if not apply:
                            continue
                        if to_plaintext:
                            if not spec.typed or kind in ("empty", "plaintext"):
                                continue
                        elif not _needs_rewrite(value, current):
                            continue
                        try:
                            plain = value if kind == "plaintext" else decrypt_field(value)
                        except FieldDecryptionError:
                            report.unreadable += 1
                            continue
                        if to_plaintext:
                            if key_id_of(plain) != "plaintext" and plain:
                                raise RuntimeError(f"{table_name}.{spec.column} decrypts to something that looks encrypted; stopping.")
                            updates[spec.column] = plain
                            report.rewritten += 1
                            continue
                        token = encrypt_field(plain)
                        if decrypt_field(token) != plain or key_id_of(token) != current:
                            raise RuntimeError(f"Verification failed for {table_name}.{spec.column}; nothing in this batch was written.")
                        updates[spec.column] = token
                        report.rewritten += 1
                    if updates:
                        connection.execute(sa.update(table).where(table.c[primary_key] == row[primary_key]).values(**updates))
                last_id = rows[-1][primary_key]
            if apply and checkpoint_path:
                checkpoint[table_name] = last_id
                checkpoint_path.write_text(json.dumps(checkpoint))
            if len(rows) < batch_size:
                break
        if apply and checkpoint_path:
            checkpoint[table_name] = ""
            checkpoint.setdefault("_done", [])
            if table_name not in checkpoint["_done"]:
                checkpoint["_done"].append(table_name)
            checkpoint_path.write_text(json.dumps(checkpoint))
    return results


def remaining(results: dict[str, dict[str, ColumnReport]]) -> int:
    """How many values are not yet under the current key (after a report-only run)."""
    current = current_key_id()
    return sum(
        count
        for reports in results.values()
        for report in reports.values()
        for kind, count in report.counts.items()
        if kind not in ("empty", current)
    )


def summary(results: dict[str, dict[str, ColumnReport]]) -> dict:
    return {
        "current_key_id": current_key_id(),
        "tables": {
            table: {column: {"counts": report.counts, "rewritten": report.rewritten, "unreadable": report.unreadable} for column, report in reports.items()}
            for table, reports in results.items()
        },
        # After an --apply run the counts describe what was found, so subtract what was rewritten.
        "not_yet_current": remaining(results) - sum(report.rewritten for reports in results.values() for report in reports.values()),
    }
