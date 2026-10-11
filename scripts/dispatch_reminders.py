"""Run by a scheduler every 5 minutes: places due reminder calls and marks missed ones.

Usage (Render cron job or any scheduler):
    python scripts/dispatch_reminders.py
Needs CAREWISE_PUBLIC_API_URL and CAREWISE_REMINDER_CRON_TOKEN in the environment.
"""

import json
import os
import sys
import urllib.request


def main() -> int:
    base = os.environ.get("CAREWISE_PUBLIC_API_URL", "https://carewise-api.onrender.com").rstrip("/")
    token = os.environ.get("CAREWISE_REMINDER_CRON_TOKEN", "")
    if not token:
        print("CAREWISE_REMINDER_CRON_TOKEN is not set.", file=sys.stderr)
        return 1
    request = urllib.request.Request(f"{base}/reminders/dispatch", data=b"", method="POST")
    request.add_header("X-CareWise-Cron-Token", token)
    # The free web service may be asleep; allow time for it to wake up.
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - our own API
        print(json.dumps(json.loads(response.read().decode())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
