import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_PATH = PROJECT_ROOT / "sample_data.json"
ASSET_FIELDS = (
    "asset_id",
    "name",
    "type",
    "location",
    "warning_limit_C",
    "critical_limit_C",
)


def load_sample_data(base_url: str) -> None:
    """Load sample assets and inspections using the running API."""
    try:
        with SAMPLE_DATA_PATH.open(encoding="utf-8") as sample_file:
            sample_data: dict[str, Any] = json.load(sample_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read {SAMPLE_DATA_PATH}: {error}") from error

    assets = sample_data.get("assets")
    inspections = sample_data.get("inspections")
    if not isinstance(assets, list) or not isinstance(inspections, list):
        raise RuntimeError("sample_data.json must contain 'assets' and 'inspections' lists.")

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as client:
        for index, asset in enumerate(assets, start=1):
            if not isinstance(asset, dict):
                raise RuntimeError(f"Asset entry {index} must be a JSON object.")

            asset_id = asset.get("asset_id", f"entry {index}")
            print(f"Loading asset {asset_id} ({index}/{len(assets)})...")
            response = client.post("/assets", json=asset)
            if response.status_code == 201:
                print(f"  Created asset {asset_id}.")
                continue
            if response.status_code == 409:
                existing_response = client.get(f"/assets/{asset_id}")
                if existing_response.status_code == 404:
                    raise RuntimeError(
                        f"Asset {asset_id} returned a duplicate conflict but could not be retrieved."
                    )
                existing_response.raise_for_status()
                existing_asset = existing_response.json()
                mismatched_fields = [
                    field
                    for field in ASSET_FIELDS
                    if existing_asset.get(field) != asset.get(field)
                ]
                if mismatched_fields:
                    raise RuntimeError(
                        f"Asset {asset_id} already exists with conflicting values in: "
                        + ", ".join(mismatched_fields)
                    )
                print(f"  Asset {asset_id} already exists with matching data; left unchanged.")
                continue
            _raise_api_error(response, f"creating asset {asset_id}")

        for index, inspection in enumerate(inspections, start=1):
            if not isinstance(inspection, dict):
                raise RuntimeError(f"Inspection entry {index} must be a JSON object.")

            asset_id = inspection.get("asset_id", "unknown asset")
            print(f"Loading inspection for {asset_id} ({index}/{len(inspections)})...")
            response = client.post("/inspections", json=inspection)
            if response.status_code == 201:
                print(f"  Created inspection {response.json()['id']}.")
            elif response.status_code == 200:
                print(f"  Matching inspection already exists (ID {response.json()['id']}); left unchanged.")
            else:
                _raise_api_error(response, f"creating inspection for {asset_id}")

    print("Sample-data loading completed.")


def _raise_api_error(response: httpx.Response, action: str) -> None:
    try:
        details = response.json()
    except ValueError:
        details = response.text
    raise RuntimeError(
        f"API error while {action}: HTTP {response.status_code}: {details}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load the project sample_data.json through the running REST API."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running API (default: http://127.0.0.1:8000).",
    )
    args = parser.parse_args()

    try:
        load_sample_data(args.base_url)
    except (httpx.HTTPError, RuntimeError) as error:
        print(f"Sample-data loading failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
