# Thermal Anomaly Detection API

A small REST API for recording thermal inspections of plant equipment and
tracking temperature-threshold alerts.

## Project overview

Operators need to record inspection readings, compare them with each asset's
temperature limits, and follow up on alerts. This project stores assets,
inspections, alerts, and alert acknowledgements in SQLite. It is a rule-based
API: it does not process thermal images or use machine learning to predict
anomalies.

## Problem statement

Inspection readings need to be recorded consistently, compared with the
correct equipment limits, and surfaced to operators when a threshold is
crossed. This API provides that recordkeeping and alert workflow.

## Key features

- Create and list assets.
- Record inspections and view an asset's inspection history.
- Automatically create warning or critical alerts from each asset's limits.
- Prevent duplicate inspection records for an asset and timestamp.
- List open alerts and acknowledge them with a separate audit-history record.
- Load and verify the supplied sample data through the REST API.

## Technology

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- SQLite
- Pydantic 2
- Pytest and HTTPX

## Project structure

```text
thermal-anomaly-api/
├── app/
│   ├── routes/
│   │   ├── alerts.py
│   │   ├── assets.py
│   │   └── inspections.py
│   ├── services/
│   ├── __init__.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   └── schemas.py
├── evidence/
│   ├── requirement_checklist.md
│   ├── sample_data_results.txt
│   └── SCREENSHOT_GUIDE.md
├── scripts/
│   ├── load_sample_data.py
│   └── verify_sample_data.py
├── tests/
│   ├── test_alerts.py
│   ├── test_assets.py
│   └── test_inspections.py
├── .gitignore
├── DESIGN_NOTES.md
├── README.md
├── WALKTHROUGH.md
├── requirements.txt
└── sample_data.json
```

The local `thermal_anomaly.db` file is created beside this README when the
application starts. It is ignored by Git and can be recreated by starting the
server and running the sample-data verification script. The `.venv` folder
contains the local Python environment and is also ignored.

## Database design

- **`assets`**: uses `asset_id` as its primary key and stores the asset's name,
  type, location, warning limit, critical limit, and creation time.
- **`inspections`**: has a database-generated primary key and a foreign key to
  `assets`. It stores the inspection timestamp, maximum and mean temperatures,
  image reference, and creation time. A unique constraint on
  `(asset_id, timestamp)` prevents duplicate inspections for the same asset
  and timestamp.
- **`alerts`**: has a database-generated primary key and a foreign key to an
  inspection. It stores severity, status, and creation time.
- **`alert_acknowledgement_history`**: has a database-generated primary key
  and a foreign key to an alert. Each row records who acknowledged the alert,
  when it happened, and the previous and new statuses.

SQLite foreign-key checks are enabled. Tables are initialized with
`create_all`, which creates missing tables without deleting existing data; it
does not migrate changes to an existing schema.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/assets` | Create an asset (`201`); duplicate ID is `409`; invalid input is `422`. |
| `GET` | `/assets` | List assets; returns an empty list when none exist. |
| `GET` | `/assets/{asset_id}` | Get an asset (`404` if unknown). |
| `POST` | `/inspections` | Save an inspection and, if needed, create its alert. |
| `GET` | `/assets/{asset_id}/inspections` | List an asset's inspections newest first (`404` if unknown). |
| `GET` | `/alerts/open` | List open alerts newest first, including asset and temperature details. |
| `POST` | `/alerts/{alert_id}/acknowledge` | Acknowledge an open alert and save its audit record. |

### Example requests

Create an asset:

```json
{
  "asset_id": "BLR-01",
  "name": "Boiler 1 shell",
  "type": "boiler",
  "location": "Boiler house",
  "warning_limit_C": 85,
  "critical_limit_C": 100
}
```

Create an inspection:

```json
{
  "asset_id": "BLR-01",
  "timestamp": "2026-11-10T09:15:00+05:30",
  "max_temp_C": 90,
  "mean_temp_C": 70,
  "image_ref": "frames/blr01_0915.csv"
}
```

Acknowledge an alert:

```json
{
  "acknowledged_by": "Sai"
}
```

The acknowledgement response includes `alert_id`, `acknowledged_by`,
`acknowledged_at`, `previous_status`, and `new_status`. Unknown alert IDs
return `404`, already acknowledged alerts return `409`, and blank names
return `422`.

## Alert-generation rules

The API reads the warning and critical limits from the asset record and
compares them with the inspection's **`max_temp_C`**:

1. At or above the critical limit: create one `critical` alert.
2. Otherwise, at or above the warning limit: create one `warning` alert.
3. Below the warning limit: create no alert.

The inspection and its alert are committed in one database transaction.
Thresholds are not hardcoded in the application.

## Idempotency and audit history

The database unique constraint on `(asset_id, timestamp)` is the final guard
against duplicate inspections. An identical request returns the existing
inspection with `200 OK`; a new inspection returns `201 Created`. If the
same asset and timestamp are sent with different temperature or image data,
the API returns `409 Conflict`. The inspection and alert share a transaction,
so a failed insert cannot leave a partial alert.

Acknowledgement is also transactional. A conditional status update only
changes an alert that is still `open`; a later attempt returns `409` and does
not add another history row. The acknowledgement and history entry commit
together. The timestamp is generated in UTC. SQLite does not preserve timezone
metadata in its native datetime storage, so stored datetime values should be
interpreted according to the API's UTC convention where applicable.

## Windows installation and setup

Open PowerShell in this project folder:

```powershell
cd "C:\path\to\thermal-anomaly-api"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell prevents environment activation, use the environment's Python
directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Start the server

From the project folder, with the environment activated:

```powershell
python -m uvicorn app.main:app --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>

## Load and verify sample data

Keep the server running. In a second PowerShell terminal, change to the project
folder and activate `.venv`, then run:

```powershell
python scripts\load_sample_data.py
```

To load the data twice, check the API and database counts, and generate the
submission report in one command, run:

```powershell
python scripts\verify_sample_data.py
```

Both scripts use the existing REST API; they do not write directly to SQLite.
Assets are sent before inspections. Existing assets are skipped only when
their API-returned values match the sample; conflicting asset data is reported
and never overwritten. Identical inspections use the API's idempotent response,
so repeating the loader does not create duplicate inspections or alerts.
Neither script acknowledges alerts or deletes records.

For the supplied sample data, the verified result is **3 assets, 3 inspections,
2 open alerts**: one `critical` alert for BLR-02 (118.4°C), one `warning`
alert for MTR-07 (76.0°C), and no alert for BLR-01 (71.2°C).
`evidence/sample_data_results.txt` contains the actual verification results.

## Run automated tests

Tests create a separate temporary SQLite database for each test. From the
project folder with `.venv` activated, run:

```powershell
python -m pytest -v
```

## Known limitations

- No frontend dashboard, authentication, or role management.
- No thermal image ingestion or processing; `image_ref` is stored as a
  reference only.
- Alert generation uses fixed, asset-configured thresholds, not ML-based
  anomaly prediction.
- SQLite is suitable for this assessment. A higher-concurrency deployment
  could use PostgreSQL.
- `create_all` is not a database migration tool; schema evolution needs a
  migration strategy.
- The project has no configured Git repository yet, so local Git status and
  commit history are unavailable.
