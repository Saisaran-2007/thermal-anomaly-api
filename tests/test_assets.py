from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "test_assets.db"
        test_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
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
            yield test_client
        finally:
            test_client.close()
            app.dependency_overrides.pop(get_db, None)
            test_engine.dispose()


def valid_asset() -> dict[str, object]:
    return {
        "asset_id": "BLR-01",
        "name": "Boiler 1 shell",
        "type": "boiler",
        "location": "Boiler house",
        "warning_limit_C": 85,
        "critical_limit_C": 100,
    }


def test_create_asset(client: TestClient) -> None:
    response = client.post("/assets", json=valid_asset())

    assert response.status_code == 201
    assert response.json()["asset_id"] == "BLR-01"
    assert response.json()["created_at"]


def test_list_assets(client: TestClient) -> None:
    empty_response = client.get("/assets")
    assert empty_response.status_code == 200
    assert empty_response.json() == []

    client.post("/assets", json=valid_asset())
    response = client.get("/assets")

    assert response.status_code == 200
    assert [asset["asset_id"] for asset in response.json()] == ["BLR-01"]


def test_get_existing_asset(client: TestClient) -> None:
    client.post("/assets", json=valid_asset())

    response = client.get("/assets/BLR-01")

    assert response.status_code == 200
    assert response.json()["name"] == "Boiler 1 shell"


def test_get_unknown_asset_returns_404(client: TestClient) -> None:
    response = client.get("/assets/UNKNOWN")

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found."


def test_duplicate_asset_returns_409(client: TestClient) -> None:
    client.post("/assets", json=valid_asset())

    response = client.post("/assets", json=valid_asset())

    assert response.status_code == 409
    assert response.json()["detail"] == "An asset with this asset_id already exists."


def test_invalid_asset_returns_422(client: TestClient) -> None:
    invalid_asset = valid_asset() | {"critical_limit_C": 80}

    response = client.post("/assets", json=invalid_asset)

    assert response.status_code == 422
