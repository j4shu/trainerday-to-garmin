# TrainerDay to Garmin Connect

Automatically uploads the latest [TrainerDay](https://trainerday.com/) indoor
cycling workout to [Garmin Connect](https://connect.garmin.com/) and names it.

## Motivation

TrainerDay can automatically export a `.fit` file of your indoor cycling workout
to your Dropbox after you finish it.

However, the file doesn't get automatically uploaded to Garmin Connect, so you
have to do it yourself - manually. Not only that, when you upload the file,
Garmin names the activity "Cycling", so you then have to rename it to something
meaningful.

The file format matters for more than convenience. Garmin computes Training
Effect and Training Load server-side for `.fit` uploads only. The TCX schema has
no fields to carry those metrics, so activities uploaded as `.tcx` never count
toward Exercise Load or Training Status.

## How It Works

This script simply automates the manual process above. When you run it, it:

1. Logs in to Garmin. The credentials are cached at `~/.garminconnect` for
   future runs.
2. Finds the most recent `.fit` file in your TrainerDay Dropbox folder.
   - Defaults to `~/Library/CloudStorage/Dropbox/Apps/TrainerDay`.
3. Parses the workout title from the filename.
   - For example, `2026-06-09 20-35-37 - Z2 60%.fit` becomes `Z2 60%`.
4. Performs the upload, then sets the activity name and type.

Editing activity fields can only happen after the initial upload. The script
handles this by snapshotting your most recent activity before upload and then
uses that to detect when the new activity appears. A pre-existing activity is
never touched.

[Intervals.icu](https://intervals.icu/) needs no handling here. It syncs from
Garmin Connect and inherits both the activity name and type, including later
renames.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- TrainerDay account configured to export `.fit` files to Dropbox
- Garmin Connect account

## Setup

Install dependencies:

```
uv sync
```

## Usage

```
uv run main.py
```
