# TrainerDay to Garmin Connect/Intervals.icu

Automatically uploads the latest [TrainerDay](https://trainerday.com/) indoor
cycling workout to [Garmin Connect](https://connect.garmin.com/) and edits it on
both Garmin Connect and [Intervals.icu](https://intervals.icu/).

## Motivation

TrainerDay can automatically export a `.tcx` file of your indoor cycling workout
to your Dropbox after you finish it.

However, the file doesn't get automatically uploaded to Garmin Connect, so you
have to do it yourself - manually. Not only that, when you upload the file,
Garmin defaults the activity type to "Cycling" and names it "Cycling", so you
then have to manually edit the activity type to "Virtual Cycling" and name it
something meaningful. The activity type is specifically important for me to
distinguish between indoor vs outdoor rides when viewing activities/totals on
Intervals.icu.

When the activity syncs to Intervals.icu, I noticed it does not carry over the
edited activity type from Garmin, so it needs it be edited there as well.

## How It Works

This script simply automates the manual process above. When you run it, it:

1. Prompts you to log in to Garmin. The credentials are cached at
   `~/.garminconnect` for future runs.
2. Finds the most recent `.tcx` file in your TrainerDay Dropbox folder.
   - Defaults to `~/Library/CloudStorage/Dropbox/Apps/TrainerDay`.
3. Parses the workout title from the filename.
   - For example, `2026-06-09 20-35-37 - Z2 60%.tcx` becomes `Z2 60%`.
4. Prompts you to confirm before uploading. Press `Enter` to continue, or any
   other key to abort without uploading.
5. Performs the upload and edits to Garmin Connect.
6. Waits for Intervals.icu to sync the activity.
7. Prompts you to confirm before editing the activity type on Intervals.icu.
8. Edits the activity type on Intervals.icu.

Editing activity fields can only happen after the initial upload. The script
handles this by snapshotting your most recent activity before upload and then
uses that to detect when the new activity appears after upload. A pre-existing
activity is never touched.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- TrainerDay account configured to export `.tcx` files to Dropbox
- Garmin Connect account
- Intervals.icu account that syncs from Garmin

## Setup

Install dependencies:

```
uv sync
```

Create `.env` file at repo root (git-ignored) for your Intervals.icu API key:

```
INTERVALS_API_KEY=<your_api_key>
```

Alternatively, export it:

```
export INTERVALS_API_KEY=<your_api_key>
```

## Usage

```
uv run main.py              # full flow
uv run main.py intervals    # re-run only the intervals.icu step
```
