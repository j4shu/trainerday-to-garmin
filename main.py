import getpass
import logging
import re
import time
from pathlib import Path

from garminconnect import Garmin

TRAINERDAY_DIR = Path("~/Library/CloudStorage/Dropbox/Apps/TrainerDay").expanduser()
TOKENSTORE = Path("~/.garminconnect").expanduser()

# TrainerDay FIT file format: "<date> <time> - <workout title>.fit", e.g.
# 2026-06-09 20-35-37 - 5x3 120%, 2x 102%.fit
TRAINERDAY_FILE_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2} - (?P<title>.+)$"
)

# Desired activity type. Payload is from `client.get_activity_types()`
ACTIVITY_TYPE_DTO = {
    "typeId": 152,
    "typeKey": "virtual_ride",
    "parentTypeId": 2,
}

log = logging.getLogger("main")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)-7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def login_to_garmin() -> Garmin:
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


def get_latest_activity_file(directory: Path) -> Path:
    """Return the most recently modified .fit file in the given directory."""
    files = [p for p in directory.glob("*.fit") if p.is_file()]
    if not files:
        raise FileNotFoundError(f"No .fit files found in: {directory}")
    return max(files, key=lambda p: p.stat().st_mtime)


def wait_for_garmin_upload(
    client: Garmin,
    last_activity: dict,
    timeout: int = 30,
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


def upload_garmin_activity(client: Garmin) -> None:
    """Upload the latest TrainerDay .fit to Garmin and edit its name/type."""
    # Find the latest FIT file exported by TrainerDay
    activity_file = get_latest_activity_file(directory=TRAINERDAY_DIR)
    log.info(f"Found latest fit file: {activity_file.name}")
    log.info(f"Full path: {activity_file.resolve()}")

    # Parse the activity name
    match = TRAINERDAY_FILE_REGEX.match(activity_file.stem)
    if not match:
        raise ValueError(
            f"Filename does not match the expected TrainerDay format "
            f"'<YYYY-MM-DD> <HH-MM-SS> - <title>': {activity_file.name}"
        )
    activity_name = match.group("title").strip()
    log.info(f"Parsed activity name: {activity_name}")

    # Save the current last activity before upload so we can recognise the newly-created one
    # and never touch a pre-existing activity.
    last_activity = client.get_last_activity()

    # Upload the new activity
    result = client.import_activity(str(activity_file))
    log.info(f"Garmin upload initiated. Result: {result}")

    # Wait for it to appear
    new_activity = wait_for_garmin_upload(client=client, last_activity=last_activity)
    new_activity_id = new_activity.get("activityId")

    # Sleep to let Garmin activity processing to settle before editing
    time.sleep(3)

    # Edit it
    activity_type = ACTIVITY_TYPE_DTO["typeKey"]
    log.info(f"Editing activity name to: {activity_name}")
    client.set_activity_name(new_activity_id, activity_name)
    log.info(f"Editing activity type to: {activity_type}")
    client.set_activity_type(new_activity_id, *ACTIVITY_TYPE_DTO.values())


def main() -> None:
    setup_logging()

    client = login_to_garmin()
    upload_garmin_activity(client=client)
    log.info("Done.")


if __name__ == "__main__":
    main()
