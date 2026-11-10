from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Alert, Inspection


@pytest.fixture
def client_and_sessions() -> Generator[
    tuple[TestClient, sessionmaker[Session]],
    None,
    None,
]:
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "test_inspections.db"
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


def create_asset(client: TestClient) -> None:
    response = client.post(
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
    assert response.status_code == 201


def inspection_data(
    *,
    timestamp: datetime | None = None,
    max_temp_C: float = 70,
    mean_temp_C: float = 65,
) -> dict[str, object]:
    return {
        "asset_id": "BLR-01",
        "timestamp": (timestamp or datetime(2026, 11, 10, 9, tzinfo=timezone.utc)).isoformat(),
        "max_temp_C": max_temp_C,
        "mean_temp_C": mean_temp_C,
        "image_ref": "frames/boiler.csv",
    }


def alert_counts(sessions: sessionmaker[Session]) -> tuple[int, int]:
    with sessions() as db:
        warning_count = db.scalar(
            select(func.count()).select_from(Alert).where(Alert.severity == "warning")
        )
        critical_count = db.scalar(
            select(func.count()).select_from(Alert).where(Alert.severity == "critical")
        )
    return warning_count or 0, critical_count or 0


def inspection_count(sessions: sessionmaker[Session]) -> int:
    with sessions() as db:
        return db.scalar(select(func.count()).select_from(Inspection)) or 0


def test_inspection_below_warning_creates_no_alert(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions
    create_asset(client)

    response = client.post("/inspections", json=inspection_data(max_temp_C=84.9))

    assert response.status_code == 201
    assert response.json()["max_temp_C"] == 84.9
    assert inspection_count(sessions) == 1
    assert alert_counts(sessions) == (0, 0)


def test_inspection_at_warning_limit_creates_warning(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions
    create_asset(client)

    response = client.post("/inspections", json=inspection_data(max_temp_C=85))

    assert response.status_code == 201
    assert alert_counts(sessions) == (1, 0)


def test_inspection_at_critical_limit_creates_critical(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions
    create_asset(client)

    response = client.post("/inspections", json=inspection_data(max_temp_C=100))

    assert response.status_code == 201
    assert alert_counts(sessions) == (0, 1)


def test_unknown_asset_returns_404(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions

    response = client.post("/inspections", json=inspection_data())

    assert response.status_code == 404
    assert inspection_count(sessions) == 0
    assert alert_counts(sessions) == (0, 0)


def test_identical_duplicate_returns_existing_without_duplicate_alert(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions
    create_asset(client)
    data = inspection_data(max_temp_C=85)

    first_response = client.post("/inspections", json=data)
    duplicate_response = client.post("/inspections", json=data)

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["id"] == first_response.json()["id"]
    assert inspection_count(sessions) == 1
    assert alert_counts(sessions) == (1, 0)


def test_conflicting_duplicate_returns_409_without_partial_records(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, sessions = client_and_sessions
    create_asset(client)
    timestamp = datetime(2026, 11, 10, 9, tzinfo=timezone.utc)

    first_response = client.post(
        "/inspections",
        json=inspection_data(timestamp=timestamp, max_temp_C=85),
    )
    conflict_response = client.post(
        "/inspections",
        json=inspection_data(timestamp=timestamp, max_temp_C=100, mean_temp_C=90),
    )

    assert first_response.status_code == 201
    assert conflict_response.status_code == 409
    assert inspection_count(sessions) == 1
    assert alert_counts(sessions) == (1, 0)


def test_inspection_history_is_newest_first(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_sessions
    create_asset(client)
    older = datetime(2026, 11, 9, 9, tzinfo=timezone.utc)
    newer = older + timedelta(days=1)
    client.post("/inspections", json=inspection_data(timestamp=older, max_temp_C=70))
    client.post("/inspections", json=inspection_data(timestamp=newer, max_temp_C=75))

    response = client.get("/assets/BLR-01/inspections")

    assert response.status_code == 200
    assert [item["timestamp"] for item in response.json()] == [
        newer.isoformat().replace("+00:00", ""),
        older.isoformat().replace("+00:00", ""),
    ]


def test_unknown_asset_history_returns_404(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_sessions

    response = client.get("/assets/UNKNOWN/inspections")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "invalid_data",
    [
        {"max_temp_C": -1},
        {"mean_temp_C": 71},
        {"timestamp": "not-a-datetime"},
    ],
)
def test_invalid_inspection_returns_422(
    client_and_sessions: tuple[TestClient, sessionmaker[Session]],
    invalid_data: dict[str, object],
) -> None:
    client, sessions = client_and_sessions
    create_asset(client)

    response = client.post("/inspections", json=inspection_data() | invalid_data)

    assert response.status_code == 422
    assert inspection_count(sessions) == 0
    assert alert_counts(sessions) == (0, 0)
