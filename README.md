# TrainerDay to Garmin Connect and Intervals.icu

Automatically uploads the latest [TrainerDay](https://trainerday.com/) indoor cycling workout to [Garmin Connect](https://connect.garmin.com/) and waits for it to sync to Intervals.icu

## Motivation

TrainerDay can export a `.fit` file of your indoor cycling workout.

However, the file doesn't get automatically uploaded to Garmin Connect, so you have to download it and do it yourself - manually. Not only that, when you upload the file, Garmin defaults the activity type to "Cycling" and names it "Cycling", so you then have to manually edit the activity type to "Virtual Cycling" and name it something meaningful. The activity type is specifically important for me to distinguish between indoor vs outdoor rides when viewing activities/totals on [Intervals.icu](https://intervals.icu/).

If you use Intervals.icu, you have to make the same edits there too.

This script simply automates the above manual process.

## How It Works

1. Logs in to Garmin. The credentials are cached at `~/.garminconnect` for future runs.
2. Fetches your most recent activity from the TrainerDay API and downloads it as a `.fit` file.
3. Patches the `.fit` file (via [`fit-tool`](https://pypi.org/project/fit-tool/)):
   - Sets `sub_sport` to `virtual_activity` so Garmin sets the type to Virtual Cycling.
   - Sets `local_timestamp` to the local timezone.
4. Uploads the patched `.fit` file, waits for Garmin to index it, then renames the activity.
5. Polls Intervals.icu until the activity syncs from Garmin.

Note: Intervals.icu needs no editing here. It syncs from Garmin Connect and inherits both the activity name and type, including renames.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- TrainerDay account, with an API key from [TrainerDay API](https://api.trainerday.com/)
- Garmin Connect account
- Intervals.icu account, with an API key from [Intervals.icu settings](https://intervals.icu/settings)

## Setup

Install dependencies:

```
uv sync
```

Create `.env` and add your API keys:

```
TRAINERDAY_API_KEY=<key>
INTERVALS_API_KEY=<key>
```

## Usage

```
uv run main.py
```
