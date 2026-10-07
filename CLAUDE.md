# CLAUDE.md

Uploads the latest TrainerDay ride to Garmin Connect as Virtual Cycling and
waits for the Intervals.icu sync. See README.md.

- `main.py`: the flow. `garmin.py`: login, .fit patching, upload polling.
  `trainerday.py` / `intervals.py`: API clients.
- Setup: `uv sync`, then `uv run pre-commit install`.
- Checks (also run by the pre-commit hook): `uv run ruff check`,
  `uv run ruff format --check`, `uv run ty check`.
- Do not run `uv run main.py` to test: it uploads to the real Garmin account and
  may prompt for login.
- No tests; `uv run python -c 'import main'` is the smoke check.
