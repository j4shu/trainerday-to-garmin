import getpass
import logging
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin
from requests import get, put
from requests.auth import HTTPBasicAuth

TRAINERDAY_DIR = Path("~/Library/CloudStorage/Dropbox/Apps/TrainerDay").expanduser()
TOKENSTORE = Path("~/.garminconnect").expanduser()

# TrainerDay TCX file format: "<date> <time> - <workout title>.tcx", e.g.
# 2026-06-09 20-35-37 - 5x3 120%, 2x 102%.tcx
TRAINERDAY_TCX_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2} - (?P<title>.+)$"
)

# Desired activity type. Payload is from `client.get_activity_types()`
ACTIVITY_TYPE_DTO = {
    "typeId": 152,
    "typeKey": "virtual_ride",
    "parentTypeId": 2,
}

INTERVALS_ICU_BASE_URL = "https://intervals.icu/api/v1"

log = logging.getLogger("main")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)-7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def garmin_login() -> Garmin:
    """
    Return an authenticated Garmin client, logging in at the start of a run.
    Reuses the cached session at TOKENSTORE when present and still valid
    (refreshing a near-expiry token); otherwise prompts for credentials (+ MFA)
    and caches a fresh session.
    """
    if TOKENSTORE.exists():
        try:
            client = Garmin()
            client.login(str(TOKENSTORE))  # validates + refreshes if near expiry
            log.info(f"Found cached Garmin session: {TOKENSTORE}.")
            return client
        except Exception as exc:
            log.warning(f"Cached session unusable: ({exc}); logging in fresh.")

    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Garmin Connect password: ")
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA/2FA code: ").strip(),
    )
    client.login(str(TOKENSTORE))  # caches tokens to TOKENSTORE
    log.info(f"Successfully logged in. Garmin session cached: {TOKENSTORE}")
    return client


def find_latest_tcx_file(directory: Path) -> Path:
    """Return the most recently modified .tcx file in the given directory."""
    files = [p for p in directory.glob("*.tcx") if p.is_file()]
    if not files:
        raise FileNotFoundError(f"No .tcx files found in: {directory}")
    return max(files, key=lambda p: p.stat().st_mtime)


def wait_for_upload(
    client: Garmin,
    last_activity: dict,
    timeout: int = 120,
    poll_interval: int = 5,
) -> dict:
    """Return the just-uploaded activity, identified as the new most-recent
    activity once Garmin finishes indexing it.
    """
    last_activity_id = last_activity.get("activityId")
    deadline = time.monotonic() + timeout
    while True:
        new_activity = client.get_last_activity()
        new_activity_id = new_activity.get("activityId")

        # If the last activity changed, that means the upload was processed and it's now the new last activity
        if new_activity_id is not None and new_activity_id != last_activity_id:
            log.info(f"Found new uploaded activity: {new_activity_id}")
            return new_activity

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Waited {timeout}s but no new activity appeared after upload; giving up."
            )
        log.info(f"No new activity yet; polling again in {poll_interval}s...")
        time.sleep(poll_interval)


def intervals_auth() -> HTTPBasicAuth:
    """HTTP Basic auth for intervals.icu."""
    key = os.environ.get("INTERVALS_API_KEY")
    if not key:
        raise SystemExit(
            "INTERVALS_API_KEY is not set. Create one at intervals.icu → "
            "Settings → Developer, then: export INTERVALS_API_KEY=your_api_key"
        )
    return HTTPBasicAuth("API_KEY", key)


def find_latest_intervals_activity() -> dict | None:
    """Return the most recent intervals.icu activity, or None if there are none."""
    resp = get(
        f"{INTERVALS_ICU_BASE_URL}/athlete/0/activities",
        params={"oldest": "2026-01-01", "limit": 1},
        auth=intervals_auth(),
        timeout=30,
    )
    resp.raise_for_status()
    activities = resp.json()
    return activities[0] if activities else None


def edit_intervals_activity_type(id: str, activity_type: str) -> None:
    """Edit the activity type of an intervals.icu activity."""
    resp = put(
        f"{INTERVALS_ICU_BASE_URL}/activity/{id}",
        json={"type": activity_type},
        auth=intervals_auth(),
        timeout=30,
    )
    resp.raise_for_status()


def trainerday_to_garmin(client: Garmin) -> None:
    """Upload the latest TrainerDay .tcx to Garmin and edit its name/type."""
    # Find the latest TCX file exported by TrainerDay
    tcx_file = find_latest_tcx_file(directory=TRAINERDAY_DIR)
    log.info(f"Found latest tcx file: {tcx_file.name}")
    log.info(f"Full path: {tcx_file.resolve()}")

    # Parse the activity name
    activity_name = TRAINERDAY_TCX_REGEX.match(tcx_file.stem).group("title").strip()
    log.info(f"Parsed activity name: {activity_name}")

    # Save the current last activity before upload so we can recognise the newly-created one
    # and never touch a pre-existing activity.
    last_activity = client.get_last_activity()

    # Upload the new activity
    result = client.import_activity(str(tcx_file))
    log.info(f"Garmin upload initiated. Result: {result}")

    # Wait for it to appear
    new_activity = wait_for_upload(client=client, last_activity=last_activity)
    new_activity_id = new_activity.get("activityId")

    # Sleep to let Garmin activity processing to settle before editing
    time.sleep(3)

    # Edit it
    activity_type = ACTIVITY_TYPE_DTO["typeKey"]
    log.info(f"Editing activity name to: {activity_name}")
    client.set_activity_name(new_activity_id, activity_name)
    log.info(f"Editing activity type to: {activity_type}")
    client.set_activity_type(new_activity_id, *ACTIVITY_TYPE_DTO.values())


def wait_for_intervals_sync(
    baseline_id: str | None,
    timeout: int = 300,
    poll_interval: int = 10,
) -> dict | None:
    """Return the newly-synced intervals.icu activity, identified as the new
    most-recent activity once it differs from the one seen before the upload.
    Returns None if it never appears within the timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        activity = find_latest_intervals_activity()
        if activity is not None and activity["id"] != baseline_id:
            return activity

        if time.monotonic() >= deadline:
            return None
        log.info(
            f"Not synced to intervals.icu yet; polling again in {poll_interval}s..."
        )
        time.sleep(poll_interval)


def garmin_to_intervals(baseline_id: str | None) -> int:
    """Edit the activity type after it syncs to intervals.icu."""
    log.info("Waiting for intervals.icu to sync...")
    intervals_activity = wait_for_intervals_sync(baseline_id=baseline_id)
    if intervals_activity is None:
        log.error(
            "Activity never synced to intervals.icu; giving up. The Garmin upload "
            "succeeded, so edit the activity type there once it appears."
        )
        return 1

    log.info(f"Found latest intervals.icu activity: {intervals_activity['name']} ")

    # Edit it
    activity_type = "VirtualRide"
    log.info(f"Editing activity type to: {activity_type}")
    edit_intervals_activity_type(
        id=intervals_activity["id"], activity_type=activity_type
    )

    log.info("Done.")
    return 0


def main() -> int:
    load_dotenv()
    setup_logging()

    # Snapshot the latest intervals.icu activity before uploading, so the newly
    # synced one can be recognised later. Also fails fast on a missing API key.
    baseline = find_latest_intervals_activity()
    baseline_id = baseline["id"] if baseline else None

    client = garmin_login()
    trainerday_to_garmin(client=client)
    return garmin_to_intervals(baseline_id=baseline_id)


if __name__ == "__main__":
    sys.exit(main())
