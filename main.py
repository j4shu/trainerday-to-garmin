import getpass
import logging
import tempfile
import time
from pathlib import Path

from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import SubSport
from garminconnect import Garmin

TRAINERDAY_DIR = Path("~/Library/CloudStorage/Dropbox/Apps/TrainerDay").expanduser()
TOKENSTORE = Path("~/.garminconnect").expanduser()

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


def set_fit_activity_type(fit_file: Path) -> Path:
    """Return a temp copy of the FIT with every session's sub_sport set to
    virtual_activity. TrainerDay writes sub_sport=generic, which Garmin files as
    plain "Cycling"; virtual_activity makes it Virtual Cycling on upload, so no
    post-upload retype is needed.
    """
    fit = FitFile.from_file(str(fit_file))
    sessions = [r.message for r in fit.records if isinstance(r.message, SessionMessage)]
    if not sessions:
        raise ValueError(f"No session message found in: {fit_file.name}")

    for session in sessions:
        session.sub_sport = SubSport.VIRTUAL_ACTIVITY

    patched_file = Path(tempfile.mkstemp(suffix=".fit")[1])
    fit.to_file(str(patched_file))
    log.info(f"Set sub_sport to virtual_activity in {len(sessions)} session(s).")
    return patched_file


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
    """Upload the latest TrainerDay .fit to Garmin and name it after the file."""
    # Find the latest FIT file exported by TrainerDay
    activity_file = get_latest_activity_file(directory=TRAINERDAY_DIR)
    log.info(f"Found latest fit file: {activity_file.name}")
    log.info(f"Full path: {activity_file.resolve()}")

    # The filename (without extension) is the activity name
    activity_name = activity_file.stem
    log.info(f"Activity name: {activity_name}")

    # Set the activity type in the file so Garmin files it as Virtual Cycling
    upload_file = set_fit_activity_type(activity_file)

    # Save the current last activity before upload so we can recognise the newly-created one
    # and never touch a pre-existing activity.
    last_activity = client.get_last_activity()

    # Upload the new activity
    result = client.import_activity(str(upload_file))
    log.info(f"Garmin upload initiated. Result: {result}")

    # Wait for it to appear
    new_activity = wait_for_garmin_upload(client=client, last_activity=last_activity)
    new_activity_id = new_activity.get("activityId")

    # Sleep to let Garmin activity processing to settle before editing
    time.sleep(3)

    # FIT carries no activity name, so it still has to be set over the API
    log.info(f"Editing activity name to: {activity_name}")
    client.set_activity_name(new_activity_id, activity_name)


def main() -> None:
    setup_logging()

    client = login_to_garmin()
    upload_garmin_activity(client=client)
    log.info("Done.")


if __name__ == "__main__":
    main()
