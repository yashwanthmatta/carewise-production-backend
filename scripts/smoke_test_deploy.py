import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Optional


def request_json(method: str, url: str, payload: Optional[dict] = None, token: str = "") -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def request_multipart(url: str, fields: dict[str, str], file_field: str, file_name: str, file_bytes: bytes, content_type: str, token: str = "") -> dict:
    boundary = f"----carewise-smoke-{int(time.time())}"
    body_parts: list[bytes] = []
    for name, value in fields.items():
        body_parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    body_parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=b"".join(body_parts), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed CareWise API.")
    parser.add_argument("--base-url", required=True, help="Example: https://carewise-api.onrender.com")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="change-me-long-password")
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep the smoke-test account and reports for manual debugging.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    email = args.email or f"smoke-{int(time.time())}@example.com"

    try:
        health = request_json("GET", f"{base_url}/health")
        features = request_json("GET", f"{base_url}/features")
        ready = request_json("GET", f"{base_url}/ready")
        signup = request_json(
            "POST",
            f"{base_url}/auth/signup",
            {"email": email, "password": args.password, "role": "patient"},
        )
        token = signup["access_token"]
        consent = request_json(
            "POST",
            f"{base_url}/consent",
            {"version": "2026-06-15", "accepted": True, "region": "US"},
            token,
        )
        profile = request_json(
            "PUT",
            f"{base_url}/patients/me/profile",
            {
                "name": "Deployment Smoke Patient",
                "date_of_birth": "1990-01-01",
                "sex_at_birth": "unknown",
                "conditions": "Smoke test only",
                "allergies": "None",
                "location_region": "US",
                "insurance_status": "some",
            },
            token,
        )
        care_plan = request_json(
            "POST",
            f"{base_url}/care-plans/generate",
            {
                "patient_id": profile["patient_id"],
                "symptom_text": "I need help preparing for a doctor visit. No chest pain.",
                "goals": ["Doctor visit preparation"],
                "diet_style": "flexible",
                "activity_level": "light",
            },
            token,
        )
        medication = request_json(
            "POST",
            f"{base_url}/patients/{profile['patient_id']}/medications",
            {
                "name": "Smoke test medication",
                "dose": "Test dose",
                "timing": "Morning",
                "notes": "Created by deploy smoke test.",
            },
            token,
        )
        report = request_json(
            "POST",
            f"{base_url}/reports/upload",
            {
                "patient_id": profile["patient_id"],
                "file_name": "smoke-report.txt",
                "content_type": "text/plain",
                "report_text": "Blood pressure follow up. No chest pain. Diabetes education requested.",
            },
            token,
        )
        analysis = request_json("POST", f"{base_url}/reports/{report['id']}/analyze", token=token)
        analyses = request_json("GET", f"{base_url}/reports/{report['id']}/analyses", token=token)
        if not analyses or analyses[0]["id"] != analysis["id"]:
            raise RuntimeError("Saved report analysis history did not return the latest analysis.")
        file_report = request_multipart(
            f"{base_url}/reports/upload-file",
            fields={
                "patient_id": profile["patient_id"],
                "report_text": "LDL cholesterol elevated. No chest pain.",
            },
            file_field="file",
            file_name="smoke-file-report.txt",
            file_bytes=b"LDL cholesterol elevated. No chest pain.",
            content_type="text/plain",
            token=token,
        )
        download = request_json("GET", f"{base_url}/reports/{file_report['id']}/download", token=token)
        recommendation = request_json(
            "POST",
            f"{base_url}/recommendations/ai",
            {
                "patient_id": profile["patient_id"],
                "context_text": "diabetes and blood pressure",
                "diet_style": "vegetarian",
                "goals": ["diet", "exercise"],
            },
            token,
        )
        doctors = request_json("GET", f"{base_url}/doctors/search?location=US-CA&specialty=primary%20care", token=token)
        insurance = request_json(
            "POST",
            f"{base_url}/insurance/match",
            {
                "location_region": "US-CA",
                "conditions": "diabetes, hypertension",
                "budget_level": "mid",
            },
            token,
        )
        subscription = request_json("POST", f"{base_url}/subscriptions/checkout", {"plan_code": "basic"}, token)
        notification = request_json(
            "POST",
            f"{base_url}/notifications/devices",
            {"channel": "push", "device_token": "smoke-device-token", "enabled": True},
            token,
        )
        export = request_json("GET", f"{base_url}/privacy/me/export", token=token)
        if (
            export["account"]["email"] != email
            or not export["patients"]
            or not export["reports"]
            or not export["report_analyses"]
            or not export["medications"]
            or not export["intakes"]
            or not export["care_plans"]
        ):
            raise RuntimeError("Privacy export did not include the smoke-test account, patient, reports, analyses, medications, intakes, and care plans.")
        deletion = {"status": "skipped"}
        if not args.keep_data:
            deletion = request_json("DELETE", f"{base_url}/privacy/me", token=token)
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "passed",
                "health": health,
                "ready": ready,
                "features": {
                    "durable_storage": features.get("durable_storage"),
                    "storage_ready": features.get("storage_ready"),
                    "report_uploads": features.get("report_uploads"),
                    "image_ocr": features.get("image_ocr"),
                    "stripe_checkout": features.get("stripe_checkout"),
                },
                "signup_email": email,
                "consent_id": consent["id"],
                "patient_id": profile["patient_id"],
                "care_plan_id": care_plan["id"],
                "risk_level": care_plan["risk_level"],
                "medication_id": medication["id"],
                "report_id": report["id"],
                "analysis_id": analysis["id"],
                "saved_analyses": len(analyses),
                "file_report_id": file_report["id"],
                "download_url_kind": "private" if download["download_url"].startswith(("http://", "https://")) else "local",
                "recommendation_items": len(recommendation["diet"]),
                "doctor_results": len(doctors["results"]),
                "insurance_matches": len(insurance["matches"]),
                "subscription_id": subscription["id"],
                "notification_id": notification["id"],
                "privacy_export_reports": len(export["reports"]),
                "privacy_export_analyses": len(export["report_analyses"]),
                "privacy_export_medications": len(export["medications"]),
                "privacy_export_intakes": len(export["intakes"]),
                "privacy_export_care_plans": len(export["care_plans"]),
                "cleanup": deletion["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
