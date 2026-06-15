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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed CareWise API.")
    parser.add_argument("--base-url", required=True, help="Example: https://carewise-api.onrender.com")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="change-me-long-password")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    email = args.email or f"smoke-{int(time.time())}@example.com"

    try:
        health = request_json("GET", f"{base_url}/health")
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
                "signup_email": email,
                "consent_id": consent["id"],
                "patient_id": profile["patient_id"],
                "care_plan_id": care_plan["id"],
                "risk_level": care_plan["risk_level"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
