import getpass
import logging
import tempfile
import time
from pathlib import Path

from garminconnect import Garmin

TRAINERDAY_DIR = Path("~/Library/CloudStorage/Dropbox/Apps/TrainerDay").expanduser()
TOKENSTORE = Path("~/.garminconnect").expanduser()

# TrainerDay writes sub_sport=generic, which Garmin files as plain "Cycling".
# Setting it to virtual_activity makes Garmin file the ride as Virtual Cycling,
# so no post-upload retype is needed. Values are from the FIT profile.
SESSION_GLOBAL_MESG_NUM = 18
SUB_SPORT_FIELD_NUM = 6
SUB_SPORT_VIRTUAL_ACTIVITY = 58

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


def fit_crc(data: bytes) -> int:
    """FIT CRC-16, per the nibble-table algorithm in the FIT SDK."""
    # fmt: off
    table = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)
    # fmt: on
    crc = 0
    for byte in data:
        for nibble in (byte & 0x0F, (byte >> 4) & 0x0F):
            tmp = table[crc & 0x0F]
            crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ table[nibble]
    return crc


def set_fit_activity_type(fit_file: Path) -> Path:
    """Return a temp copy of the FIT with every session's sub_sport set to
    virtual_activity. Patches the single byte in place and recomputes the file
    CRC, so everything else in the file is preserved exactly.
    """
    data = bytearray(fit_file.read_bytes())
    end = data[0] + int.from_bytes(data[4:8], "little")  # header + data size
    pos, definitions, patched = data[0], {}, 0

    while pos < end:
        record_header = data[pos]
        pos += 1

        if record_header & 0x80:  # compressed timestamp: data, never a definition
            pos += definitions[(record_header >> 5) & 0x03]["size"]
            continue

        local_num = record_header & 0x0F
        if record_header & 0x40:  # definition message
            pos += 1  # reserved
            endian = "big" if data[pos] else "little"
            pos += 1
            global_num = int.from_bytes(data[pos : pos + 2], endian)
            pos += 2
            num_fields = data[pos]
            pos += 1
            fields = []
            for _ in range(num_fields):
                fields.append((data[pos], data[pos + 1]))
                pos += 3
            dev_size = 0
            if record_header & 0x20:  # developer fields follow
                num_dev = data[pos]
                pos += 1
                for _ in range(num_dev):
                    dev_size += data[pos + 1]
                    pos += 3
            definitions[local_num] = {
                "global_num": global_num,
                "fields": fields,
                "size": sum(size for _, size in fields) + dev_size,
            }
            continue

        definition = definitions[local_num]
        if definition["global_num"] == SESSION_GLOBAL_MESG_NUM:
            offset = pos
            for field_num, field_size in definition["fields"]:
                if field_num == SUB_SPORT_FIELD_NUM:
                    data[offset] = SUB_SPORT_VIRTUAL_ACTIVITY
                    patched += 1
                    break
                offset += field_size
        pos += definition["size"]

    if not patched:
        raise ValueError(f"No session sub_sport field found in: {fit_file.name}")

    data[end : end + 2] = fit_crc(bytes(data[:end])).to_bytes(2, "little")
    patched_file = Path(tempfile.mkstemp(suffix=".fit")[1])
    patched_file.write_bytes(data)
    log.info(f"Set sub_sport to virtual_activity in {patched} session message(s).")
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
