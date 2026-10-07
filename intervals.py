import logging
import os
import time
from datetime import datetime

import requests

INTERVALS_API = "https://intervals.icu/api/v1"
POLL_TIMEOUT = 60
POLL_INTERVAL = 5

log = logging.getLogger(__name__)


def poll_intervals_icu_sync(expected_activity_id: int, expected_activity_name: str):
    """Verify Intervals.icu has synced a Garmin activity."""
    oldest = datetime.now().astimezone().date().isoformat()
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        response = requests.get(
            f"{INTERVALS_API}/athlete/0/activities",
            params={"oldest": oldest, "limit": 1, "fields": "id,name,external_id"},
            auth=("API_KEY", os.environ["INTERVALS_API_KEY"]),
            timeout=30,
        )
        response.raise_for_status()
        for activity in response.json():
            if (
                activity.get("external_id") == str(expected_activity_id)
                and activity.get("name") == expected_activity_name
            ):
                log.info(f"Synced to Intervals.icu: {activity['name']}")
                return

        if time.monotonic() >= deadline:
            log.warning(
                f"Waited {POLL_TIMEOUT}s but Intervals.icu has not synced yet; giving up."
            )
            return
        log.info(
            f"Not synced to Intervals.icu yet; polling again in {POLL_INTERVAL}s..."
        )
        time.sleep(POLL_INTERVAL)
