import logging
import os

import requests

TRAINERDAY_API = "https://api.trainerday.com/api/v1"

log = logging.getLogger(__name__)


def trainerday_get(path: str, **kwargs) -> requests.Response:
    """GET from the TrainerDay API, authenticated with TRAINERDAY_API_KEY."""
    response = requests.get(
        f"{TRAINERDAY_API}{path}",
        headers={"Authorization": f"Bearer {os.environ['TRAINERDAY_API_KEY']}"},
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
    log.info(f"Found TrainerDay activity: {activity['name']}")
    return activity


def download_trainerday_fit(activity_id: str) -> bytes:
    """Download a TrainerDay activity's .fit file."""
    content = trainerday_get(path=f"/activities/{activity_id}/fit").content
    return content
