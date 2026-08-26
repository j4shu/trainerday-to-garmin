import getpass
import logging
import tempfile
import time
from pathlib import Path

from fit_tool import FitFile
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
        # force, because fit_tool calls basicConfig on import, which would no-op this
        force=True,
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


def get_latest_fit_file(directory: Path) -> Path:
    """Return the most recently modified .fit file in the given directory."""
    files = [p for p in directory.glob("*.fit") if p.is_file()]
    if not files:
        raise FileNotFoundError(f"No .fit files found in: {directory}")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    log.info(f"Found .fit file: {latest.resolve()}")
    return latest


def prepare_fit_file(fit_file: Path) -> Path:
    """Return a temp copy of the FIT with every session's sub_sport set to
    virtual_activity, so Garmin files it as Virtual Cycling instead of Cycling.
    """
    log.info("Preparing .fit file for Garmin upload...")
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


def wait_for_new_activity(
    garmin_client: Garmin,
    previous_activity: dict,
    timeout: int = 30,
    poll_interval: int = 5,
) -> dict:
    """Return the just-uploaded activity, identified as the new most-recent activity
    once Garmin finishes indexing it.
    """
    previous_id = previous_activity.get("activityId")
    deadline = time.monotonic() + timeout
    while True:
        activity = garmin_client.get_last_activity()
        activity_id = activity.get("activityId")
        if activity_id is not None and activity_id != previous_id:
            log.info(f"Found new uploaded activity: {activity_id}")
            return activity

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Waited {timeout}s but no new activity appeared after upload; giving up."
            )
        log.info(f"No new activity yet; polling again in {poll_interval}s...")
        time.sleep(poll_interval)


def main() -> None:
    setup_logging()

    garmin_client = login_to_garmin()
    # record latest activity before upload so the new activity is never confused with an existing one
    previous_activity = garmin_client.get_last_activity()

    # patch the fit file and upload it
    fit_file = get_latest_fit_file(directory=TRAINERDAY_DIR)
    patched_fit_file = prepare_fit_file(fit_file=fit_file)
    result = garmin_client.import_activity(str(patched_fit_file))
    log.info(f"Garmin upload initiated. Result: {result}")

    # wait for it to show up
    new_activity = wait_for_new_activity(
        garmin_client=garmin_client, previous_activity=previous_activity
    )

    # rename it
    activity_name = fit_file.stem
    log.info(f"Editing activity name to: {activity_name}")
    garmin_client.set_activity_name(new_activity.get("activityId"), activity_name)


if __name__ == "__main__":
    main()
