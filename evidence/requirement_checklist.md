# Assessment Requirement Checklist

Compared against the supplied `Task_Brief_Backend_API.pdf` and the current
implementation. Statuses below are based on source files and observed tests
or API verification, not documentation alone.

| # | Requirement | Status | Evidence |
|---:|---|---|---|
| 1 | Database schema for assets, inspections, alerts | **PASS** | `app/models.py`: `Asset`, `Inspection`, `Alert`; the acknowledgement-history table is also implemented. |
| 2 | Primary keys, foreign keys, timestamps | **PASS** | `app/models.py`: keys and timestamp columns; SQLite foreign-key enforcement is enabled in `app/database.py`. |
| 3 | Create asset API | **PASS** | `POST /assets` in `app/routes/assets.py`; tested in `tests/test_assets.py`. |
| 4 | List assets API | **PASS** | `GET /assets` in `app/routes/assets.py`; tested in `tests/test_assets.py`. |
| 5 | Create inspection API | **PASS** | `POST /inspections` in `app/routes/inspections.py`; tested in `tests/test_inspections.py`. |
| 6 | List one asset's inspections newest first | **PASS** | `GET /assets/{asset_id}/inspections`; sorting test in `tests/test_inspections.py`. |
| 7 | List open alerts API | **PASS** | `GET /alerts/open` in `app/routes/alerts.py`; open, excluded, empty, sorted, and detail behavior tested in `tests/test_alerts.py`. |
| 8 | Acknowledge alert, including who and when | **PASS** | `POST /alerts/{alert_id}/acknowledge`; success and audit tests in `tests/test_alerts.py`. |
| 9 | Critical alert at or above critical limit | **PASS** | Critical threshold uses the asset record and `max_temp_C`; tested in `tests/test_inspections.py`; sample API result verified. |
| 10 | Warning alert at or above warning limit when below critical | **PASS** | Warning threshold is the second branch after critical; tested in `tests/test_inspections.py`; sample API result verified. |
| 11 | No alert below warning threshold | **PASS** | Tested directly in `tests/test_inspections.py`; sample BLR-01 result verified. |
| 12 | Idempotent inspection creation | **PASS** | Unique `(asset_id, timestamp)` constraint, identical retry (`200`), conflicting retry (`409`), and record counts tested. |
| 13 | Acknowledgement audit trail | **PASS** | Separate `AlertAcknowledgementHistory` row stores actor, time, and status transition; duplicate/failed acknowledgement tests verify history counts. |
| 14 | Automated tests (at least five for full marks) | **PASS** | `python -m pytest -v`: 25 tests passed at final review; tests use temporary SQLite databases. |
| 15 | Load sample data through the API and show alerts | **PASS** | `scripts/load_sample_data.py` posts through REST endpoints; `scripts/verify_sample_data.py` repeats and verifies; `evidence/sample_data_results.txt` records observed results. |
| 16 | README documentation | **PASS** | `README.md` documents setup, endpoints, design, tests, and sample-data demonstration. |
| 17 | Design choices and AI usage disclosure | **PASS** | `DESIGN_NOTES.md` records design choices, limitations, future improvements, and ChatGPT/GitHub Copilot use. |

## Scope notes

- The brief permits PostgreSQL or SQLite; this project uses SQLite.
- The brief's title mentions a dashboard, but its API tasks and deliverables
  do not require a frontend. No dashboard is included.
- The brief requires a screenshot **or output** demonstrating sample alerts.
  The checked-in text output is in `evidence/sample_data_results.txt`.
  Screenshots have not been captured; see `evidence/SCREENSHOT_GUIDE.md`.
- The brief requests honest AI disclosure. It is included in
  `DESIGN_NOTES.md`.
