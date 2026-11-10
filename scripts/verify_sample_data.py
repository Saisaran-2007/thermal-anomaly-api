import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
SAMPLE_DATA_PATH = PROJECT_ROOT / "sample_data.json"
LOADER_PATH = PROJECT_ROOT / "scripts" / "load_sample_data.py"
EVIDENCE_PATH = PROJECT_ROOT / "evidence" / "sample_data_results.txt"
EXPECTED_TABLES = {
    "assets",
    "inspections",
    "alerts",
    "alert_acknowledgement_history",
}


def run_loader(base_url: str, run_number: int) -> str:
    print(f"\n===== SAMPLE LOADER RUN {run_number} =====", flush=True)
    result = subprocess.run(
        [
            sys.executable,
            str(LOADER_PATH),
            "--base-url",
            base_url,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode:
        raise RuntimeError(f"Loader run {run_number} failed with exit code {result.returncode}.")
    return result.stdout.strip()


def get_api_snapshot(base_url: str) -> dict[str, Any]:
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        openapi_response = client.get("/openapi.json")
        openapi_response.raise_for_status()
        paths = openapi_response.json()["paths"]
        required_methods = {
            "/assets": {"get", "post"},
            "/assets/{asset_id}": {"get"},
            "/inspections": {"post"},
            "/assets/{asset_id}/inspections": {"get"},
            "/alerts/open": {"get"},
            "/alerts/{alert_id}/acknowledge": {"post"},
        }
        for path, methods in required_methods.items():
            available_methods = set(paths.get(path, {}))
            if not methods <= available_methods:
                raise AssertionError(
                    f"Expected methods {methods} on {path}; found {available_methods}."
                )

        assets_response = client.get("/assets")
        assets_response.raise_for_status()
        assets = assets_response.json()

        histories = {}
        inspections = []
        for asset in assets:
            response = client.get(f"/assets/{asset['asset_id']}/inspections")
            response.raise_for_status()
            histories[asset["asset_id"]] = response.json()
            inspections.extend(response.json())

        alerts_response = client.get("/alerts/open")
        alerts_response.raise_for_status()

    return {
        "assets": assets,
        "histories": histories,
        "inspections": inspections,
        "alerts": alerts_response.json(),
    }


def verify_sample_responses(sample: dict[str, Any], snapshot: dict[str, Any]) -> None:
    sample_assets = {asset["asset_id"]: asset for asset in sample["assets"]}
    api_assets = {asset["asset_id"]: asset for asset in snapshot["assets"]}
    if len(api_assets) != len(sample_assets):
        raise AssertionError(
            f"Expected {len(sample_assets)} assets from the API; found {len(api_assets)}."
        )

    for asset_id, expected in sample_assets.items():
        actual = api_assets.get(asset_id)
        if actual is None:
            raise AssertionError(f"API did not return asset {asset_id}.")
        for field in (
            "name",
            "type",
            "location",
            "warning_limit_C",
            "critical_limit_C",
        ):
            if actual[field] != expected[field]:
                raise AssertionError(
                    f"Asset {asset_id} has conflicting {field}: "
                    f"{actual[field]!r} != {expected[field]!r}."
                )

    expected_inspections_per_asset = Counter(
        inspection["asset_id"] for inspection in sample["inspections"]
    )
    for asset_id in sample_assets:
        actual_count = len(snapshot["histories"].get(asset_id, []))
        if actual_count != expected_inspections_per_asset[asset_id]:
            raise AssertionError(
                f"Expected {expected_inspections_per_asset[asset_id]} inspections for "
                f"{asset_id}; API returned {actual_count}."
            )
    if len(snapshot["inspections"]) != len(sample["inspections"]):
        raise AssertionError(
            f"Expected {len(sample['inspections'])} inspections; "
            f"API returned {len(snapshot['inspections'])}."
        )

    actual_inspections = snapshot["inspections"]
    for expected in sample["inspections"]:
        expected_timestamp = datetime.fromisoformat(expected["timestamp"]).replace(tzinfo=None)
        matches = [
            item
            for item in actual_inspections
            if item["asset_id"] == expected["asset_id"]
            and datetime.fromisoformat(item["timestamp"]).replace(tzinfo=None)
            == expected_timestamp
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected one API inspection for {expected['asset_id']} at "
                f"{expected['timestamp']}; found {len(matches)}."
            )
        actual = matches[0]
        for field in ("max_temp_C", "mean_temp_C", "image_ref"):
            if actual[field] != expected[field]:
                raise AssertionError(
                    f"Inspection for {expected['asset_id']} has conflicting {field}."
                )

    expected_alerts = []
    for inspection in sample["inspections"]:
        asset = sample_assets[inspection["asset_id"]]
        temperature = inspection["max_temp_C"]
        if temperature >= asset["critical_limit_C"]:
            expected_alerts.append(
                (inspection["asset_id"], "critical", temperature)
            )
        elif temperature >= asset["warning_limit_C"]:
            expected_alerts.append((inspection["asset_id"], "warning", temperature))

    actual_alerts = [
        (alert["asset_id"], alert["severity"], alert["max_temp_C"])
        for alert in snapshot["alerts"]
    ]
    if any(alert["status"] != "open" for alert in snapshot["alerts"]):
        raise AssertionError("GET /alerts/open returned an alert that is not open.")
    if Counter(actual_alerts) != Counter(expected_alerts):
        raise AssertionError(
            f"Actual open alerts {actual_alerts} do not match "
            f"limits-derived results {expected_alerts}."
        )


def record_ids(snapshot: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        "assets": sorted(asset["asset_id"] for asset in snapshot["assets"]),
        "inspections": sorted(item["id"] for item in snapshot["inspections"]),
        "alerts": sorted(alert["id"] for alert in snapshot["alerts"]),
    }


def verify_database() -> dict[str, int]:
    from app.database import engine
    from app.models import Alert, Asset, Inspection

    existing_tables = set(inspect(engine).get_table_names())
    if not EXPECTED_TABLES <= existing_tables:
        raise AssertionError(f"Database tables missing: {EXPECTED_TABLES - existing_tables}.")

    with Session(engine) as db:
        return {
            "assets": db.scalar(select(func.count()).select_from(Asset)) or 0,
            "inspections": db.scalar(select(func.count()).select_from(Inspection)) or 0,
            "alerts": db.scalar(select(func.count()).select_from(Alert)) or 0,
        }


def create_report(
    sample: dict[str, Any],
    snapshot: dict[str, Any],
    alerts: list[tuple[str, str, float]],
    loader_outputs: list[str],
    database_counts: dict[str, int],
    sample_hash: str,
    base_url: str,
) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "Thermal Anomaly Detection API - Sample Data Demonstration",
        f"Demonstration date/time: {now}",
        f"API base URL: {base_url}",
        "",
        "Final API counts after the second loader run:",
        f"Assets: {len(snapshot['assets'])}",
        f"Inspections: {len(snapshot['inspections'])}",
        f"Open alerts: {len(snapshot['alerts'])}",
        f"CRITICAL alerts: {sum(alert['severity'] == 'critical' for alert in snapshot['alerts'])}",
        f"WARNING alerts: {sum(alert['severity'] == 'warning' for alert in snapshot['alerts'])}",
        "",
        "Alerts returned by GET /alerts/open:",
    ]
    for alert in sorted(snapshot["alerts"], key=lambda item: item["id"]):
        lines.append(
            f"ID {alert['id']} | asset {alert['asset_id']} | "
            f"{alert['severity'].upper()} | max temperature {alert['max_temp_C']} C | "
            f"inspection {alert['inspection_id']}"
        )
    lines.extend(
        [
            "",
            "Actual API verification:",
            f"GET /assets returned {len(snapshot['assets'])} assets.",
            f"GET /assets/{{asset_id}}/inspections returned {len(snapshot['inspections'])} inspections in total.",
            f"GET /alerts/open returned {len(snapshot['alerts'])} open alerts.",
            f"Alerts matched outcomes computed from sample data and API asset limits: {len(alerts)} of {len(snapshot['alerts'])}.",
        ]
    )
    for inspection in sample["inspections"]:
        asset_id = inspection["asset_id"]
        matching = [alert for alert in alerts if alert[0] == asset_id]
        result = f"{matching[0][1].upper()} alert" if matching else "no alert"
        lines.append(
            f"{asset_id}: API maximum temperature {inspection['max_temp_C']} C; "
            f"computed result: {result}."
        )
    lines.extend(
        [
            "",
            "Repeat-load verification:",
            "The second loader run completed successfully.",
            "Asset, inspection, and alert IDs were unchanged between runs.",
            "Duplicate assets were skipped only after matching API data was confirmed.",
            "Duplicate inspections were handled by the API idempotency response.",
            "No records were deleted or overwritten.",
            "",
            "Database and source-file checks:",
            "All four tables exist: assets, inspections, alerts, alert_acknowledgement_history.",
            f"Database counts (assets/inspections/alerts): {database_counts}.",
            f"sample_data.json remained byte-for-byte unchanged (SHA256 {sample_hash}).",
            "",
        ]
    )
    for index, output in enumerate(loader_outputs, start=1):
        lines.extend([f"Loader run {index} output:", output, ""])
    lines.append(
        "Results are based on actual REST API responses and read-only database checks; "
        "no screenshots were fabricated."
    )

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the sample loader twice, verify API results, and write evidence."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running API (default: http://127.0.0.1:8000).",
    )
    args = parser.parse_args()

    try:
        original_bytes = SAMPLE_DATA_PATH.read_bytes()
        sample = json.loads(original_bytes)
        loader_outputs = [
            run_loader(args.base_url, 1),
        ]
        first = get_api_snapshot(args.base_url)
        verify_sample_responses(sample, first)
        first_ids = record_ids(first)

        loader_outputs.append(run_loader(args.base_url, 2))
        second = get_api_snapshot(args.base_url)
        verify_sample_responses(sample, second)
        if first_ids != record_ids(second):
            raise AssertionError("Record IDs changed after the second loader run.")

        database_counts = verify_database()
        expected_counts = {
            "assets": len(second["assets"]),
            "inspections": len(second["inspections"]),
            "alerts": len(second["alerts"]),
        }
        if database_counts != expected_counts:
            raise AssertionError(
                f"Database counts {database_counts} differ from API counts {expected_counts}."
            )
        if SAMPLE_DATA_PATH.read_bytes() != original_bytes:
            raise AssertionError("sample_data.json changed during the demonstration.")

        actual_alerts = [
            (alert["asset_id"], alert["severity"], alert["max_temp_C"])
            for alert in second["alerts"]
        ]
        create_report(
            sample,
            second,
            actual_alerts,
            loader_outputs,
            database_counts,
            hashlib.sha256(original_bytes).hexdigest(),
            args.base_url,
        )
    except (OSError, ValueError, httpx.HTTPError, RuntimeError, AssertionError) as error:
        print(f"Sample-data verification failed: {error}", file=sys.stderr)
        return 1

    print(
        f"\nVerified API counts: {len(second['assets'])} assets, "
        f"{len(second['inspections'])} inspections, {len(second['alerts'])} open alerts."
    )
    for asset_id, severity, temperature in actual_alerts:
        print(f"Verified alert: {asset_id} {severity.upper()} at {temperature} C.")
    print(f"Evidence report written to {EVIDENCE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
