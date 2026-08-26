# TrainerDay to Garmin Connect

Automatically uploads the latest [TrainerDay](https://trainerday.com/) indoor cycling workout to [Garmin Connect](https://connect.garmin.com/).

## Motivation

TrainerDay can export a `.fit` file of your indoor cycling workout.

However, the file doesn't get automatically uploaded to Garmin Connect, so you have to download it and do it yourself - manually. Not only that, when you upload the file, Garmin defaults the activity type to "Cycling" and names it "Cycling", so you then have to manually edit the activity type to "Virtual Cycling" and name it something meaningful. The activity type is specifically important for me to distinguish between indoor vs outdoor rides when viewing activities/totals on [Intervals.icu](https://intervals.icu/).

If you also use Intervals.icu, you have to make the same edits there too.

This script simply automates the above manual process.

## How It Works

1. Logs in to Garmin. The credentials are cached at `~/.garminconnect` for future runs.
2. Fetches your most recent activity from the [TrainerDay API](https://api.trainerday.com/) and downloads its `.fit` file. The activity name comes back as a field, so there is nothing to parse.
3. Patches a temp copy of the `.fit` file (via [`fit-tool`](https://pypi.org/project/fit-tool/)) and sets `sub_sport` to `virtual_activity` so Garmin sets the type to Virtual Cycling.
4. Uploads the patched file, waits for Garmin to index it, then renames the activity.

Note: Intervals.icu needs no handling here. It syncs from Garmin Connect and inherits both the activity name and type, including renames.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- TrainerDay account, with an API key from [trainerday.com/developer](https://api.trainerday.com/developer)
- Garmin Connect account

## Setup

Install dependencies:

```
uv sync
```

Put your TrainerDay API key in `.env`:

```
TRAINERDAY_API_KEY=td_your_api_key
```

## Usage

```
uv run main.py
```
