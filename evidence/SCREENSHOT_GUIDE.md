# Screenshot Guide

No screenshots are included yet. Capture genuine screenshots on your machine;
do not use mock or edited API results as evidence.

## Before capturing

1. Open the project folder in VS Code.
2. Activate `.venv` in a PowerShell terminal.
3. Start the server with `python -m uvicorn app.main:app --reload`.
4. If the demo data is not present, run `python scripts\verify_sample_data.py`
   from another terminal while the server is running.

## Recommended screenshots

1. **VS Code project structure:** Expand `app`, `app/routes`, `tests`,
   `scripts`, and `evidence` in Explorer so the implementation and test
   structure are visible.
2. **Swagger endpoints:** Open `http://127.0.0.1:8000/docs`. Capture the
   available asset, inspection, and alert endpoints.
3. **Three assets:** In Swagger, expand `GET /assets`, choose **Try it out**,
   then **Execute**. Capture the successful response showing the assets.
4. **Two open alerts:** Expand `GET /alerts/open`, choose **Try it out**, then
   **Execute**. Capture both the critical BLR-02 and warning MTR-07 results.
5. **Acknowledgement (optional):** Use `POST /alerts/{alert_id}/acknowledge`
   with `{"acknowledged_by":"Your Name"}` only if you are comfortable changing
   that alert from open to acknowledged in the demo database. Capture the
   successful response. This reduces the open-alert count; do this after
   capturing the two-open-alert screenshot, or use a disposable database.
6. **Passing tests:** In the project terminal, run `python -m pytest -v` and
   capture the final summary showing all tests passing.
7. **Sample verification report:** Open
   `evidence/sample_data_results.txt` in VS Code and capture the actual counts,
   alerts, and repeat-load results.

Save screenshots as separate image files in this `evidence` folder. This guide
does not claim that screenshots have already been captured.
