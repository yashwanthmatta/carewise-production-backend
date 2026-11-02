"""Versioned field encryption, key rotation and the field migration tool. Synthetic data only."""

import json
import logging

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core import crypto
from app.core.config import settings
from app.core.crypto import FieldDecryptionError, decrypt_field, encrypt_field, key_id_of
from app.db.session import engine
from app.main import create_app
from app.services import field_encryption_migration as migration
from tests.api.test_reports_and_access_control import auth_headers, create_profile


KEY_2 = Fernet.generate_key().decode()
KEY_3 = Fernet.generate_key().decode()
SYNTHETIC_TEST = "Synthetic ferritin marker"
SYNTHETIC_VALUE = "5.40"


@pytest.fixture(autouse=True)
def key_settings(monkeypatch):
    """Each test starts with only the original key and restores the ring afterwards."""
    monkeypatch.setattr(settings, "field_encryption_keys", "")
    monkeypatch.setattr(settings, "field_encryption_current_key_id", "")
    crypto.reset_key_ring_cache()
    yield monkeypatch
    crypto.reset_key_ring_cache()


def use_keys(monkeypatch, keys: str, current: str) -> None:
    monkeypatch.setattr(settings, "field_encryption_keys", keys)
    monkeypatch.setattr(settings, "field_encryption_current_key_id", current)
    crypto.reset_key_ring_cache()


def raw_rows(table: str, *columns: str) -> list[dict]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(sa.text(f"SELECT {', '.join(columns)} FROM {table}")).mappings()]


def save_trend(client, headers, patient_id, **overrides):
    payload = {"patient_id": patient_id, "test_name": SYNTHETIC_TEST, "value": SYNTHETIC_VALUE, "unit": "ng/mL", "observed_on": "2026-07-01", "flag": "low"}
    payload.update(overrides)
    response = client.post("/lab-trends", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- the cipher itself -------------------------------------------------------------------

def test_values_name_their_key_and_round_trip():
    token = encrypt_field("synthetic note")
    assert token.startswith("ftenc:k1:")
    assert key_id_of(token) == "k1"
    assert decrypt_field(token) == "synthetic note"
    assert encrypt_field("") == "" and decrypt_field("") == ""


def test_same_text_encrypts_differently_each_time():
    assert encrypt_field("synthetic") != encrypt_field("synthetic")


def test_bare_tokens_from_before_key_ids_still_decrypt():
    legacy = crypto._legacy_fernet(settings.clean_field_encryption_key).encrypt(b"older synthetic value").decode()
    assert key_id_of(legacy) == "legacy"
    assert decrypt_field(legacy) == "older synthetic value"


def test_wrong_key_raises_instead_of_returning_a_placeholder(key_settings):
    token = encrypt_field("synthetic")
    tampered = token[:-6] + ("AAAAAA" if not token.endswith("AAAAAA") else "BBBBBB")
    with pytest.raises(FieldDecryptionError):
        decrypt_field(tampered)
    other = Fernet(KEY_3).encrypt(b"synthetic").decode()
    with pytest.raises(FieldDecryptionError):
        decrypt_field(other)


def test_unknown_key_id_raises():
    with pytest.raises(FieldDecryptionError) as error:
        decrypt_field("ftenc:k9:" + Fernet(KEY_2).encrypt(b"x").decode())
    assert error.value.key_id == "k9"


def test_decrypt_failure_logs_key_id_but_never_the_value(caplog):
    token = encrypt_field("synthetic secret marker")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FieldDecryptionError):
            decrypt_field(token.replace("ftenc:k1:", "ftenc:k1:x"))
    assert "k1" in caplog.text
    assert "synthetic secret marker" not in caplog.text
    assert token not in caplog.text


def test_bytes_are_versioned_too():
    blob = crypto.encrypt_bytes(b"%PDF synthetic")
    assert blob.startswith(b"ftenc:k1:")
    assert crypto.decrypt_bytes(blob) == b"%PDF synthetic"
    assert crypto.decrypt_bytes(crypto._legacy_fernet(settings.clean_field_encryption_key).encrypt(b"old")) == b"old"


# --- key ring configuration --------------------------------------------------------------

def test_rotation_writes_with_new_key_and_reads_old(key_settings):
    old = encrypt_field("synthetic before rotation")
    use_keys(key_settings, f"k2:{KEY_2}", "k2")
    new = encrypt_field("synthetic after rotation")
    assert key_id_of(old) == "k1" and key_id_of(new) == "k2"
    assert decrypt_field(old) == "synthetic before rotation"
    assert decrypt_field(new) == "synthetic after rotation"


def test_removing_a_key_too_early_fails_loudly(key_settings):
    use_keys(key_settings, f"k2:{KEY_2}", "k2")
    token = encrypt_field("synthetic")
    use_keys(key_settings, f"k3:{KEY_3}", "k3")
    with pytest.raises(FieldDecryptionError):
        decrypt_field(token)


@pytest.mark.parametrize(
    "keys,current,message",
    [
        ("k2", "", "must look like"),
        ("k2:not-a-key", "", "not a valid Fernet key"),
        (f"k1:{KEY_2}", "", "k1 is CAREWISE_FIELD_ENCRYPTION_KEY"),
        (f"k2:{KEY_2},k2:{KEY_3}", "", "appears twice"),
        (f"k2:{KEY_2}", "k5", "not a configured key id"),
    ],
)
def test_malformed_key_settings_are_rejected(key_settings, keys, current, message):
    use_keys(key_settings, keys, current)
    with pytest.raises(ValueError) as error:
        settings.field_encryption_key_ring
    assert message in str(error.value)
    assert KEY_2 not in str(error.value) and KEY_3 not in str(error.value)


# --- what reaches the database -----------------------------------------------------------

def test_lab_values_are_encrypted_at_rest_and_keep_their_precision():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)
        save_trend(client, headers, patient_id)
        stored = raw_rows("lab_trends", "test_name", "value", "unit", "flag")[0]
        for column, value in stored.items():
            assert value.startswith("ftenc:k1:"), column
        assert SYNTHETIC_TEST not in json.dumps(stored) and SYNTHETIC_VALUE not in json.dumps(stored)
        listed = client.get(f"/lab-trends?patient_id={patient_id}", headers=headers).json()[0]
        assert (listed["test_name"], listed["value"], listed["unit"], listed["flag"]) == (SYNTHETIC_TEST, "5.40", "ng/mL", "low")


def test_lab_test_names_stay_out_of_the_audit_log():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)
        save_trend(client, headers, patient_id)
        audit = json.dumps(raw_rows("audit_events", "action", "metadata_json"))
        assert "lab_trend_saved" in audit
        assert SYNTHETIC_TEST not in audit


def test_care_plan_and_profile_fields_are_encrypted_at_rest():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)
        plan = client.post(
            "/care-plans/generate",
            json={"patient_id": patient_id, "symptom_text": "synthetic mild headache", "goals": ["synthetic goal"], "diet_style": "vegetarian", "activity_level": "low"},
            headers=headers,
        )
        assert plan.status_code in (200, 201), plan.text
        for table, columns in {
            "patient_profiles": ("sex_at_birth", "location_region", "insurance_status"),
            "intakes": ("goals_json", "diet_style", "activity_level"),
            "care_plans": ("emergency_flags_json", "matched_conditions_json", "recommendation_json"),
        }.items():
            for row in raw_rows(table, *columns):
                for column, value in row.items():
                    assert value == "" or value.startswith("ftenc:"), f"{table}.{column}"
        dump = json.dumps(raw_rows("intakes", "goals_json", "diet_style")) + json.dumps(raw_rows("patient_profiles", "location_region"))
        assert "synthetic goal" not in dump and "vegetarian" not in dump and "US-CA" not in dump


def test_a_row_that_cannot_be_decrypted_returns_an_error_not_blank_data():
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)
        save_trend(client, headers, patient_id)
        with engine.begin() as connection:
            connection.execute(sa.text("UPDATE lab_trends SET value = 'ftenc:k1:gAAAAAbroken'"))
        response = client.get(f"/lab-trends?patient_id={patient_id}", headers=headers)
        assert response.status_code == 500
        assert "could not be read" in response.json()["detail"]
        assert "5.40" not in response.text


# --- migrating existing rows ---------------------------------------------------------------

def insert_plaintext_trends(client, count: int) -> tuple[dict, str]:
    headers, _ = auth_headers(client)
    patient_id = create_profile(client, headers)
    for index in range(count):
        save_trend(client, headers, patient_id, value=f"{index}.50")
    # Put the rows back to the plaintext form older releases wrote.
    with engine.begin() as connection:
        for row in connection.execute(sa.text("SELECT id FROM lab_trends ORDER BY id")).mappings().all():
            number = connection.execute(sa.text("SELECT COUNT(*) FROM lab_trends WHERE id < :id"), {"id": row["id"]}).scalar()
            connection.execute(
                sa.text("UPDATE lab_trends SET test_name = :t, value = :v, unit = 'ng/mL', flag = 'low' WHERE id = :id"),
                {"t": SYNTHETIC_TEST, "v": f"{number}.50", "id": row["id"]},
            )
    return headers, patient_id


def values_via_api(client, headers, patient_id) -> list[str]:
    return sorted(item["value"] for item in client.get(f"/lab-trends?patient_id={patient_id}", headers=headers).json())


def test_plaintext_rows_stay_readable_then_migrate_idempotently(tmp_path):
    with TestClient(create_app()) as client:
        headers, patient_id = insert_plaintext_trends(client, 5)
        before = values_via_api(client, headers, patient_id)
        assert before == ["0.50", "1.50", "2.50", "3.50", "4.50"]

        report = migration.summary(migration.run(engine, only_tables={"lab_trends"}))
        assert report["tables"]["lab_trends"]["value"]["counts"] == {"plaintext": 5}
        assert all(row["value"] == f"{index}.50" for index, row in enumerate(sorted(raw_rows("lab_trends", "value"), key=lambda r: r["value"])))

        applied = migration.summary(migration.run(engine, apply=True, batch_size=2, checkpoint_path=tmp_path / "cp.json", only_tables={"lab_trends"}))
        assert applied["tables"]["lab_trends"]["value"]["rewritten"] == 5
        assert applied["not_yet_current"] == 0
        assert all(row["value"].startswith("ftenc:k1:") for row in raw_rows("lab_trends", "value"))
        assert values_via_api(client, headers, patient_id) == before

        again = migration.summary(migration.run(engine, apply=True, checkpoint_path=tmp_path / "cp2.json", only_tables={"lab_trends"}))
        assert sum(column["rewritten"] for column in again["tables"]["lab_trends"].values()) == 0


def test_an_interrupted_migration_resumes_without_losing_rows(tmp_path, monkeypatch):
    with TestClient(create_app()) as client:
        headers, patient_id = insert_plaintext_trends(client, 6)
        before = values_via_api(client, headers, patient_id)
        checkpoint = tmp_path / "cp.json"

        real_encrypt = migration.encrypt_field
        calls = {"n": 0}

        def failing_encrypt(value):
            calls["n"] += 1
            if calls["n"] > 9:  # part way through the second batch
                raise KeyboardInterrupt
            return real_encrypt(value)

        monkeypatch.setattr(migration, "encrypt_field", failing_encrypt)
        with pytest.raises(KeyboardInterrupt):
            migration.run(engine, apply=True, batch_size=2, checkpoint_path=checkpoint, only_tables={"lab_trends"})
        saved = json.loads(checkpoint.read_text())
        assert saved["lab_trends"]  # progress recorded after the first finished batch
        assert values_via_api(client, headers, patient_id) == before  # the half batch was rolled back

        monkeypatch.setattr(migration, "encrypt_field", real_encrypt)
        migration.run(engine, apply=True, batch_size=2, checkpoint_path=checkpoint, only_tables={"lab_trends"})
        assert all(row["value"].startswith("ftenc:") for row in raw_rows("lab_trends", "value"))
        assert values_via_api(client, headers, patient_id) == before
        assert migration.remaining(migration.run(engine, only_tables={"lab_trends"})) == 0


def test_rotation_moves_every_value_to_the_new_key(key_settings, tmp_path):
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)
        save_trend(client, headers, patient_id)
        use_keys(key_settings, f"k2:{KEY_2}", "k2")
        before = client.get(f"/lab-trends?patient_id={patient_id}", headers=headers).json()

        pending = migration.run(engine)
        assert migration.remaining(pending) > 0
        migration.run(engine, apply=True, checkpoint_path=tmp_path / "rotate.json")
        after_counts = migration.summary(migration.run(engine))
        assert after_counts["not_yet_current"] == 0
        assert {key for table in after_counts["tables"].values() for column in table.values() for key in column["counts"]} <= {"k2", "empty"}
        assert client.get(f"/lab-trends?patient_id={patient_id}", headers=headers).json() == before

        # Only now is the old key no longer needed.
        use_keys(key_settings, f"k2:{KEY_2}", "k2")
        assert client.get(f"/lab-trends?patient_id={patient_id}", headers=headers).json() == before


def test_unreadable_values_are_counted_and_left_alone(tmp_path):
    with TestClient(create_app()) as client:
        headers, patient_id = insert_plaintext_trends(client, 2)
        with engine.begin() as connection:
            first = connection.execute(sa.text("SELECT id FROM lab_trends ORDER BY id LIMIT 1")).scalar()
            connection.execute(sa.text("UPDATE lab_trends SET unit = 'ftenc:k7:gAAAAAbroken' WHERE id = :id"), {"id": first})
        result = migration.summary(migration.run(engine, apply=True, checkpoint_path=tmp_path / "cp.json", only_tables={"lab_trends"}))
        assert result["tables"]["lab_trends"]["unit"]["unreadable"] == 1
        assert raw_rows("lab_trends", "unit")[0]["unit"] == "ftenc:k7:gAAAAAbroken" or "ftenc:k7:gAAAAAbroken" in [r["unit"] for r in raw_rows("lab_trends", "unit")]


def test_tool_output_never_contains_values(tmp_path, capsys):
    from scripts.security import encrypt_fields

    with TestClient(create_app()) as client:
        insert_plaintext_trends(client, 2)
        encrypt_fields.main(["--apply", "--checkpoint", str(tmp_path / "cp.json"), "--table", "lab_trends"])
    printed = capsys.readouterr().out
    assert SYNTHETIC_TEST not in printed and "0.50" not in printed
    assert json.loads(printed)["not_yet_current"] == 0


def test_rollback_to_plaintext_only_touches_newly_encrypted_columns(tmp_path):
    with TestClient(create_app()) as client:
        headers, patient_id = insert_plaintext_trends(client, 3)
        client.post(
            "/lab-trends",
            json={"patient_id": patient_id, "test_name": SYNTHETIC_TEST, "value": "9.90", "unit": "ng/mL", "notes": "synthetic note"},
            headers=headers,
        )
        migration.run(engine, apply=True, checkpoint_path=tmp_path / "a.json")
        before = values_via_api(client, headers, patient_id)
        migration.run(engine, apply=True, to_plaintext=True, checkpoint_path=tmp_path / "b.json")
        rows = raw_rows("lab_trends", "value", "encrypted_notes")
        assert sorted(row["value"] for row in rows) == before
        assert all(row["encrypted_notes"] == "" or row["encrypted_notes"].startswith("ftenc:") for row in rows)
        assert values_via_api(client, headers, patient_id) == before


def test_rollback_flag_needs_explicit_confirmation():
    from scripts.security import encrypt_fields

    with pytest.raises(SystemExit):
        encrypt_fields.main(["--to-plaintext", "--apply"])


def test_k1_can_be_retired_only_with_another_current_key(key_settings):
    key_settings.setattr(settings, "field_encryption_key1_retired", True)
    use_keys(key_settings, "", "")
    with pytest.raises(ValueError):
        settings.field_encryption_key_ring
    use_keys(key_settings, f"k2:{KEY_2}", "k2")
    assert crypto.configured_key_ids() == ["k2"]
    with pytest.raises(FieldDecryptionError):
        decrypt_field("ftenc:k1:" + Fernet(KEY_3).encrypt(b"x").decode())
    assert decrypt_field(encrypt_field("synthetic")) == "synthetic"
