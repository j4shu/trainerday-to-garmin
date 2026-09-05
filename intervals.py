import logging
import os
import time
from datetime import datetime

import requests

INTERVALS_API = "https://intervals.icu/api/v1"

log = logging.getLogger(__name__)


def intervals_icu_get(path: str, **kwargs) -> requests.Response:
    """GET from the Intervals.icu API. authenticated with INTERVALS_API_KEY."""
    response = requests.get(
        f"{INTERVALS_API}{path}",
        auth=("API_KEY", os.environ["INTERVALS_API_KEY"]),
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response


def poll_intervals_icu_sync(
    expected_activity_id: int,
    expected_activity_name: str,
    timeout: int = 60,
    poll_interval: int = 5,
) -> dict | None:
    """Verify Intervals.icu has synced a Garmin activity."""
    oldest = datetime.now().astimezone().date().isoformat()
    deadline = time.monotonic() + timeout
    while True:
        activities = intervals_icu_get(
            path="/athlete/0/activities",
            params={
                "oldest": oldest,
                "limit": 1,
                "fields": "id,name,external_id",
            },
        ).json()
        for activity in activities:
            if (
                activity.get("external_id") == str(expected_activity_id)
                and activity.get("name") == expected_activity_name
            ):
                log.info(f"Synced to Intervals.icu: {activity['name']}")
                return activity

        if time.monotonic() >= deadline:
            log.warning(
                f"Waited {timeout}s but Intervals.icu has not synced yet; giving up."
            )
            return None
        log.info(
            f"Not synced to Intervals.icu yet; polling again in {poll_interval}s..."
        )
        time.sleep(poll_interval)
