import logging
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from garmin import garmin_login, modify_fit, poll_new_garmin_activity
from intervals import poll_intervals_icu_sync
from trainerday import download_trainerday_fit, get_latest_trainerday_activity

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)-7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        # force, because fit_tool calls basicConfig on import, which would no-op this
        force=True,
    )
    load_dotenv()
    # fail before the run touches Garmin if any required API key is missing
    missing = [
        n for n in ("TRAINERDAY_API_KEY", "INTERVALS_API_KEY") if not os.environ.get(n)
    ]
    if missing:
        raise RuntimeError(f"Not set: {', '.join(missing)}. Add to .env")

    garmin_client = garmin_login()

    # record latest activity before upload so the new activity is never confused with an existing one
    previous_activity = garmin_client.get_last_activity()

    trainerday_activity = get_latest_trainerday_activity()
    fit_bytes = download_trainerday_fit(activity_id=trainerday_activity["id"])

    patched_fit_bytes = modify_fit(fit_bytes=fit_bytes)
    fit_file = Path(tempfile.mkstemp(suffix=".fit")[1])
    fit_file.write_bytes(patched_fit_bytes)

    result = garmin_client.import_activity(str(fit_file))
    log.info(f"Garmin upload initiated. Result: {result}")
    new_activity = poll_new_garmin_activity(
        garmin_client=garmin_client, previous_activity=previous_activity
    )

    activity_name = trainerday_activity["name"]
    log.info(f"Changing Garmin activity name to: {activity_name}")
    garmin_client.set_activity_name(str(new_activity["activityId"]), activity_name)

    poll_intervals_icu_sync(
        expected_activity_id=new_activity["activityId"],
        expected_activity_name=activity_name,
    )
    log.info("Done.")


if __name__ == "__main__":
    main()
