# TrainerDay to Garmin Connect

Automatically uploads the latest [TrainerDay](https://trainerday.com/) indoor
cycling workout to [Garmin Connect](https://connect.garmin.com/) and names it.

## Motivation

TrainerDay can automatically export a `.fit` file of your indoor cycling workout
to your Dropbox after you finish it.

However, the file doesn't get automatically uploaded to Garmin Connect, so you
have to do it yourself - manually. Not only that, TrainerDay writes the FIT with
`sub_sport=generic`, so Garmin files the ride as plain "Cycling" and names it
"Cycling", leaving you to fix both by hand.

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
3. Takes the activity name from the filename, so name the file after the
   workout before running.
   - For example, `Z2 60%.fit` becomes `Z2 60%`.
4. Patches `sub_sport` to `virtual_activity` in a temp copy of the file, so
   Garmin files the ride as Virtual Cycling with no post-upload retype. This is
   a single-byte edit plus a CRC recompute; nothing else in the file changes.
5. Uploads the patched file, then sets the activity name.

FIT carries no activity-name field, so the name still has to be set over the API
after upload. The script snapshots your most recent activity before uploading
and uses that to detect when the new one appears. A pre-existing activity is
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
