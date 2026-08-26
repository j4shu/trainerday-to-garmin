import getpass
import logging
import tempfile
from pathlib import Path

from fit_tool.definition_message import DefinitionMessage
from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.profile_type import Sport, SubSport
from fit_tool.record import Record
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


def prepare_fit(fit_file: Path, activity_name: str) -> Path:
    """Return a temp copy of the FIT that Garmin will file as Virtual Cycling under
    activity_name, so nothing has to be fixed up over the API after upload.

    TrainerDay writes sub_sport=generic and no workout message, which lands as a
    plain, default-named "Cycling". Setting every session's sub_sport to
    virtual_activity fixes the type, and a workout message carrying wkt_name sets
    the title: Garmin names an activity after its workout when the file has one.
    """
    fit = FitFile.from_file(str(fit_file))

    sessions = [r.message for r in fit.records if isinstance(r.message, SessionMessage)]
    if not sessions:
        raise ValueError(f"No session message found in: {fit_file.name}")
    for session in sessions:
        session.sub_sport = SubSport.VIRTUAL_ACTIVITY

    workout = WorkoutMessage()
    workout.workout_name = activity_name
    workout.sport = Sport.CYCLING
    workout.sub_sport = SubSport.VIRTUAL_ACTIVITY
    workout.num_valid_steps = 1
    definition = DefinitionMessage.from_data_message(workout)
    workout.set_definition_message(definition)

    # file_id must stay first, so the workout goes directly after it
    index = (
        next(
            i for i, r in enumerate(fit.records) if isinstance(r.message, FileIdMessage)
        )
        + 1
    )
    fit.records.insert(index, Record.from_message(workout))
    fit.records.insert(index, Record.from_message(definition))
    fit.mark_dirty()

    patched_file = Path(tempfile.mkstemp(suffix=".fit")[1])
    fit.to_file(str(patched_file))
    log.info(
        f"Set virtual_activity in {len(sessions)} session(s), named {activity_name!r}."
    )
    return patched_file


def upload_garmin_activity(client: Garmin) -> None:
    """Upload the latest TrainerDay .fit to Garmin, named after the file."""
    activity_file = get_latest_activity_file(directory=TRAINERDAY_DIR)
    log.info(f"Found latest fit file: {activity_file.name}")
    log.info(f"Full path: {activity_file.resolve()}")

    # The filename (without extension) is the activity name
    activity_name = activity_file.stem
    log.info(f"Activity name: {activity_name}")

    upload_file = prepare_fit(activity_file, activity_name)

    result = client.import_activity(str(upload_file))
    log.info(f"Garmin upload initiated. Result: {result}")


def main() -> None:
    setup_logging()

    client = login_to_garmin()
    upload_garmin_activity(client=client)
    log.info("Done.")


if __name__ == "__main__":
    main()
