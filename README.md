# TrainerDay to Garmin Connect

Automatically uploads the latest [TrainerDay](https://trainerday.com/) indoor
cycling workout to [Garmin Connect](https://connect.garmin.com/), named and typed.

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
4. Patches a temp copy of the file (via
   [`fit-tool`](https://pypi.org/project/fit-tool/)), leaving your original
   untouched. Both settings live on the session message:
   - `sub_sport` becomes `virtual_activity`, so Garmin files the ride as Virtual
     Cycling.
   - `sport_profile_name` (field 110) becomes the activity name.
5. Uploads the patched file. Nothing is edited over the API afterwards, so there
   is no waiting on Garmin to index the activity first.

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
