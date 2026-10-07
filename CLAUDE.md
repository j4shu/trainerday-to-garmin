- Never run `uv run main.py` to test: it uploads to the real Garmin account.
- Checks: `uv run prek run -a`.
- For ad-hoc API calls, load keys with `uv run --env-file .env ...`. Never print
  key values; only send GET requests.
- API refs:
  - Intervals.icu https://intervals.icu/api/v1/docs (OpenAPI)
  - TrainerDay https://api.trainerday.com/ (HTML only)
  - Garmin has no public API (read `garminconnect` source in `.venv`)
