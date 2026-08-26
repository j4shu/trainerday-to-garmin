import getpass
import logging
import os
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from fit_tool import FitFile
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import SubSport
from garminconnect import Garmin

TRAINERDAY_API = "https://api.trainerday.com/api/v1"
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
            # validates + refreshes if near expiry
            client.login(tokenstore=str(TOKENSTORE))
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
    client.login(tokenstore=str(TOKENSTORE))  # caches tokens to TOKENSTORE
    log.info(f"Successfully logged in. Garmin session cached: {TOKENSTORE}")
    return client


def trainerday_get(path: str, **kwargs) -> requests.Response:
    """GET from the TrainerDay API, authenticated with TRAINERDAY_API_KEY."""
    api_key = os.environ.get("TRAINERDAY_API_KEY")
    if not api_key:
        raise RuntimeError("TRAINERDAY_API_KEY is not set; add it to .env")
    response = requests.get(
        f"{TRAINERDAY_API}{path}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response


def get_latest_trainerday_activity() -> dict:
    """Return the most recent TrainerDay activity; the API lists them newest first."""
    page = trainerday_get(path="/activities", params={"page": 1, "pageSize": 1}).json()
    if not page["data"]:
        raise ValueError("No TrainerDay activities found.")
    activity = page["data"][0]
    log.info(
        f"Found TrainerDay activity: {activity['name']} ({activity['startDateUTC']})"
    )
    return activity


def download_fit_file(activity_id: str) -> Path:
    """Download a TrainerDay activity's .fit file to a temp file."""
    content = trainerday_get(path=f"/activities/{activity_id}/fit").content
    fit_file = Path(tempfile.mkstemp(suffix=".fit")[1])
    fit_file.write_bytes(content)
    log.info(f"Downloaded .fit file ({len(content)} bytes): {fit_file}")
    return fit_file


def prepare_fit_file(fit_file: Path) -> Path:
    """Return a temp copy of the FIT with every session's sub_sport set to
    virtual_activity, so Garmin files it as Virtual Cycling instead of Cycling.
    """
    log.info("Preparing .fit file for Garmin upload...")
    fit = FitFile.from_file(path=str(fit_file))
    sessions = [r.message for r in fit.records if isinstance(r.message, SessionMessage)]
    if not sessions:
        raise ValueError(f"No session message found in: {fit_file.name}")

    for session in sessions:
        session.sub_sport = SubSport.VIRTUAL_ACTIVITY

    patched_file = Path(tempfile.mkstemp(suffix=".fit")[1])
    fit.to_file(path=str(patched_file))
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
    load_dotenv()

    garmin_client = login_to_garmin()
    # record latest activity before upload so the new activity is never confused with an existing one
    previous_activity = garmin_client.get_last_activity()

    # fetch the latest TrainerDay activity, then patch its fit file and upload it
    trainerday_activity = get_latest_trainerday_activity()
    fit_file = download_fit_file(activity_id=trainerday_activity["id"])
    patched_fit_file = prepare_fit_file(fit_file=fit_file)
    result = garmin_client.import_activity(activity_path=str(patched_fit_file))
    log.info(f"Garmin upload initiated. Result: {result}")

    # wait for it to show up
    new_activity = wait_for_new_activity(
        garmin_client=garmin_client, previous_activity=previous_activity
    )

    # rename it
    activity_name = trainerday_activity["name"]
    log.info(f"Editing activity name to: {activity_name}")
    garmin_client.set_activity_name(
        activity_id=new_activity.get("activityId"), title=activity_name
    )
    log.info("Done.")


if __name__ == "__main__":
    main()
