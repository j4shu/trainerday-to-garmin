# CLAUDE.md

Uploads the latest TrainerDay ride to Garmin Connect as Virtual Cycling and
waits for the Intervals.icu sync. See README.md.

- `main.py`: the flow. `garmin.py`: login, .fit patching, upload polling.
  `trainerday.py` / `intervals.py`: API clients.
- Setup: `uv sync`, then `uv run prek install`.
- Checks (also run by the pre-commit hook): `uv run ruff check`,
  `uv run ruff format --check`, `uv run ty check`.
- Do not run `uv run main.py` to test: it uploads to the real Garmin account and
  may prompt for login.
- No tests; `uv run python -c 'import main'` is the smoke check.
- `.env` (gitignored) holds `TRAINERDAY_API_KEY` and `INTERVALS_API_KEY`. Load
  it for ad-hoc calls with `set -a; . ./.env; set +a` or
  `uv run --env-file .env ...`. Never print key values and only send GET
  requests.

## APIs

- Intervals.icu: OpenAPI spec at https://intervals.icu/api/v1/docs (viewer:
  https://intervals.icu/api-docs.html). Basic auth, user `API_KEY`, password
  `$INTERVALS_API_KEY`.
- TrainerDay: no OpenAPI spec; docs at https://api.trainerday.com/.
  `Authorization: Bearer $TRAINERDAY_API_KEY`.
- Garmin Connect: no public API; the reference is the `garminconnect` package
  source in `.venv`.
