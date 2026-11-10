# 10-Minute Technical Walkthrough

## 1. Introduction and problem statement — 1 minute

This project is a small API for thermal equipment inspections. It stores
assets and their temperature readings, compares each reading with limits
configured for that asset, and tracks alerts that an operator may acknowledge.
It is a rule-based demonstration, not an AI prediction system.

## 2. Architecture and folder structure — 1 minute

FastAPI receives HTTP requests. Pydantic schemas validate incoming and
outgoing data. Route modules contain the endpoint logic. SQLAlchemy models
describe the tables and relationships, and SQLite stores the data.
`app/main.py` registers the routers and initializes missing tables.
`tests/` contains API tests; `scripts/` loads and verifies the sample data;
`evidence/` contains the measured demonstration report.

## 3. Database schema and relationships — 1.5 minutes

`assets` stores equipment names, locations, and warning and critical limits.
Each `inspections` row references an asset and stores a timestamp, maximum
and mean temperatures, and image reference. A unique constraint on the
asset ID and timestamp prevents duplicate inspections.

An `alerts` row references the inspection that triggered it. An
`alert_acknowledgement_history` row references the alert and preserves who
acknowledged it, when, and the status transition. These foreign keys connect
records without copying all of their details.

## 4. API endpoints — 2 minutes

`POST /assets` creates an asset; `GET /assets` lists them; and
`GET /assets/{asset_id}` retrieves one. `POST /inspections` records a
validated inspection and may create an alert. `GET
/assets/{asset_id}/inspections` returns the history newest first.

`GET /alerts/open` lists open alerts with related asset and temperature
details. `POST /alerts/{alert_id}/acknowledge` changes an open alert's status
and records the acknowledgement. Swagger at `/docs` lets an assessor try
these endpoints interactively.

## 5. Temperature alert-generation logic — 1.5 minutes

The inspection endpoint reads both limits from the database for the selected
asset and evaluates `max_temp_C`. If it meets or exceeds the critical limit,
one critical alert is created. Otherwise, if it meets or exceeds the warning
limit, one warning alert is created. Below the warning limit, no alert is
created. Critical is checked first so a high reading cannot be downgraded to
a warning.

The supplied sample produces no alert for BLR-01 at 71.2°C, a critical alert
for BLR-02 at 118.4°C, and a warning alert for MTR-07 at 76.0°C.

## 6. Idempotency and audit trail — 1 minute

Idempotency means repeating the same request has no additional effect. The
database uniqueness rule identifies an inspection by asset and timestamp.
An identical retry returns the saved inspection; conflicting data for that
identity returns `409 Conflict`.

Acknowledgements use a conditional update and one transaction for both the
status change and audit row. After the first success, another request gets
`409` and cannot add a second history entry.

## 7. Automated tests and sample-data demonstration — 1 minute

The tests use disposable SQLite databases, so test records do not go into the
project database. Run `python -m pytest -v`. The sample-data verification
script posts assets then inspections through the API, runs twice, and compares
API results and record IDs. The evidence report records the demonstrated
counts and alerts.

## 8. Conclusion and future improvements — 1 minute

The project demonstrates the required API, data relationships, threshold
logic, duplicate handling, audit history, and automated tests. Future work
could add a dashboard, authentication and roles, real camera integration,
notifications, PostgreSQL, and more advanced anomaly detection. Those are not
implemented in this submission.

## Likely assessor questions

**Why did you choose FastAPI?**  
It supports typed request/response validation and provides interactive API
documentation with little setup.

**Why did you use SQLite?**  
It is easy to run for a local assessment and is sufficient for this sample
workload.

**What is an ORM?**  
An object-relational mapper lets the code work with database rows as Python
objects. SQLAlchemy provides that mapping here.

**What is idempotency?**  
Repeating an identical request does not create another record or change the
result.

**Why use `max_temp_C` instead of `mean_temp_C`?**  
The peak can exceed a safe limit even when the average temperature does not.

**What happens when an inspection is submitted twice?**  
An identical asset-and-timestamp record returns the existing inspection.
Different values for that identity receive `409 Conflict`.

**How are alerts generated?**  
The maximum temperature is compared with the asset's database-stored limits:
critical first, warning second, otherwise no alert.

**How do you prevent duplicate acknowledgements?**  
A conditional update only succeeds while the alert is still open. Status and
history are committed together.

**What is an audit trail?**  
It is a separate history record showing who acknowledged an alert, when, and
the previous and new statuses.

**How did you test the application?**  
Pytest and FastAPI's test client exercise the HTTP endpoints using temporary
SQLite databases, then the sample demonstration is verified through the
running REST API.

**What would you improve in production?**  
Add authentication and roles, migrations, PostgreSQL, monitoring and
notifications, and a user-facing dashboard.
