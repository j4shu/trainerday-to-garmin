import getpass
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from fit_tool import FitFile
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import SubSport
from fit_tool.utils.conversions import to_seconds_since_1989_epoch
from garminconnect import Garmin

TOKENSTORE = Path("~/.garminconnect").expanduser()

log = logging.getLogger(__name__)


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
            # validates + refreshes if near expiry
            client.login(str(TOKENSTORE))
            log.info(f"Found cached Garmin session: {TOKENSTORE}.")
            return client
        except Exception as exc:
            log.warning(f"Cached session unusable: ({exc}); logging in fresh.")

    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Garmin Connect password: ")
    client = Garmin(
        email,
        password,
        prompt_mfa=lambda: input("MFA/2FA code: ").strip(),
    )
    client.login(str(TOKENSTORE))  # caches tokens to TOKENSTORE
    log.info(f"Successfully logged in. Garmin session cached: {TOKENSTORE}")
    return client


def modify_fit(fit_bytes: bytes) -> bytes:
    """Modify the FIT's sub_sport to virtual_activity and set local timezone."""
    fit = FitFile.from_bytes(fit_bytes)
    sessions = [r.message for r in fit.records if isinstance(r.message, SessionMessage)]
    if not sessions:
        raise ValueError("No session message found in the .fit file.")

    # change to virtual activity
    for session in sessions:
        session.sub_sport = SubSport.VIRTUAL_ACTIVITY
    log.info("Set sub_sport to virtual_activity.")

    # set local timezone
    activities = [
        r.message for r in fit.records if isinstance(r.message, ActivityMessage)
    ]
    if not activities:
        raise ValueError("No activity message found in the .fit file.")
    for activity in activities:
        utc = datetime.fromtimestamp(activity.timestamp / 1000, tz=UTC)
        local = utc.astimezone()
        offset = local.utcoffset()
        # fit_tool exposes timestamp as unix ms, but local_timestamp in the FIT wire format
        activity.local_timestamp = to_seconds_since_1989_epoch(
            activity.timestamp + int(offset.total_seconds() * 1000)
        )
        log.info(f"Set local timezone to {local.tzname()}")

    return fit.to_bytes()


def poll_new_garmin_activity(
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
        log.info(f"No new Garmin activity yet; polling again in {poll_interval}s...")
        time.sleep(poll_interval)
