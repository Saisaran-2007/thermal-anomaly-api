from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Alert, AlertAcknowledgementHistory, Inspection


@pytest.fixture
def client_and_sessions() -> Generator[
    tuple[TestClient, sessionmaker[Session]],
    None,
    None,
]:
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "test_alerts.db"
        test_engine = create_engine(f"sqlite:///{database_path.as_posix()}")

        @event.listens_for(test_engine, "connect")
        def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=test_engine)
        TestingSessionLocal = sessionmaker(
            bind=test_engine,
            autocommit=False,
            autoflush=False,
        )

        def override_get_db() -> Generator[Session, None, None]:
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app)
        try:
            yield test_client, TestingSessionLocal
        finally:
            test_client.close()
            app.dependency_overrides.pop(get_db, None)
            test_engine.dispose()


@pytest.fixture
def seeded_alerts(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> tuple[TestClient, sessionmaker[Session], int, int]:
    client, sessions = client_and_sessions
    asset_response = client.post(
        "/assets",
        json={
            "asset_id": "BLR-01",
            "name": "Boiler 1 shell",
            "type": "boiler",
            "location": "Boiler house",
            "warning_limit_C": 85,
            "critical_limit_C": 100,
        },
    )
    assert asset_response.status_code == 201

    alert_ids = []
    for index, temperature in enumerate((90, 110)):
        inspection_response = client.post(
            "/inspections",
            json={
                "asset_id": "BLR-01",
                "timestamp": datetime(2026, 11, 10, 9 + index, tzinfo=timezone.utc).isoformat(),
                "max_temp_C": temperature,
                "mean_temp_C": 70,
                "image_ref": f"frames/boiler_{index}.csv",
            },
        )
        assert inspection_response.status_code == 201
        with sessions() as db:
            alert = db.scalar(
                select(Alert).where(
                    Alert.inspection_id == inspection_response.json()["id"]
                )
            )
            assert alert is not None
            alert_ids.append(alert.id)

    return client, sessions, alert_ids[0], alert_ids[1]


def history_count(sessions: sessionmaker[Session], alert_id: int) -> int:
    with sessions() as db:
        return (
            db.scalar(
                select(func.count())
                .select_from(AlertAcknowledgementHistory)
                .where(AlertAcknowledgementHistory.alert_id == alert_id)
            )
            or 0
        )


def test_open_alerts_include_related_details_and_exclude_acknowledged(
    seeded_alerts: tuple[TestClient, sessionmaker[Session], int, int],
) -> None:
    client, sessions, first_alert_id, second_alert_id = seeded_alerts
    acknowledgement = client.post(
        f"/alerts/{first_alert_id}/acknowledge",
        json={"acknowledged_by": "Sai"},
    )
    assert acknowledgement.status_code == 200

    response = client.get("/alerts/open")

    assert response.status_code == 200
    assert len(response.json()) == 1
    alert = response.json()[0]
    assert alert["id"] == second_alert_id
    assert alert["asset_id"] == "BLR-01"
    assert alert["inspection_id"]
    assert alert["severity"] == "critical"
    assert alert["status"] == "open"
    assert alert["created_at"]
    assert alert["max_temp_C"] == 110
    assert alert["mean_temp_C"] == 70
    assert history_count(sessions, first_alert_id) == 1


def test_open_alerts_returns_empty_list_when_none_exist(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_sessions

    response = client.get("/alerts/open")

    assert response.status_code == 200
    assert response.json() == []


def test_open_alerts_are_sorted_newest_first(
    seeded_alerts: tuple[TestClient, sessionmaker[Session], int, int],
) -> None:
    client, _, first_alert_id, second_alert_id = seeded_alerts

    response = client.get("/alerts/open")

    assert response.status_code == 200
    assert [alert["id"] for alert in response.json()] == [
        second_alert_id,
        first_alert_id,
    ]


def test_acknowledgement_updates_alert_and_records_audit_history(
    seeded_alerts: tuple[TestClient, sessionmaker[Session], int, int],
) -> None:
    client, sessions, alert_id, _ = seeded_alerts

    response = client.post(
        f"/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": "Sai"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["alert_id"] == alert_id
    assert body["acknowledged_by"] == "Sai"
    assert datetime.fromisoformat(body["acknowledged_at"]).utcoffset() == timezone.utc.utcoffset(None)
    assert body["previous_status"] == "open"
    assert body["new_status"] == "acknowledged"

    with sessions() as db:
        alert = db.get(Alert, alert_id)
        history = db.scalars(
            select(AlertAcknowledgementHistory).where(
                AlertAcknowledgementHistory.alert_id == alert_id
            )
        ).all()
        assert alert is not None
        assert alert.status == "acknowledged"
        assert len(history) == 1
        assert history[0].acknowledged_by == "Sai"
        assert history[0].previous_status == "open"
        assert history[0].new_status == "acknowledged"
        assert history[0].acknowledged_at is not None


def test_unknown_alert_returns_404_without_history(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions

    response = client.post("/alerts/999/acknowledge", json={"acknowledged_by": "Sai"})

    assert response.status_code == 404
    assert history_count(sessions, 999) == 0


def test_already_acknowledged_alert_returns_409_without_duplicate_history(
    seeded_alerts: tuple[TestClient, sessionmaker[Session], int, int],
) -> None:
    client, sessions, alert_id, _ = seeded_alerts
    first_response = client.post(
        f"/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": "Sai"},
    )
    second_response = client.post(
        f"/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": "Someone else"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert history_count(sessions, alert_id) == 1
    with sessions() as db:
        history = db.scalar(
            select(AlertAcknowledgementHistory).where(
                AlertAcknowledgementHistory.alert_id == alert_id
            )
        )
        assert history is not None
        assert history.acknowledged_by == "Sai"


@pytest.mark.parametrize("acknowledged_by", ["", "   "])
def test_blank_acknowledger_returns_422_without_changes(
    seeded_alerts: tuple[TestClient, sessionmaker[Session], int, int],
    acknowledged_by: str,
) -> None:
    client, sessions, alert_id, _ = seeded_alerts

    response = client.post(
        f"/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": acknowledged_by},
    )

    assert response.status_code == 422
    assert history_count(sessions, alert_id) == 0
    with sessions() as db:
        alert = db.get(Alert, alert_id)
        assert alert is not None
        assert alert.status == "open"
