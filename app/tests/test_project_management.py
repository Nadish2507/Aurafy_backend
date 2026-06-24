import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import projects as projects_api
from app.core.config import settings
from app.models.project import Project
from app.models.user import User


@pytest.fixture
def user_auth(client: TestClient) -> dict:
    email = f"phase6_{uuid.uuid4().hex}@example.com"
    password = "securepassword123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "user_id": uuid.UUID(me["id"]),
    }


@pytest.fixture
def other_user_auth(client: TestClient) -> dict:
    email = f"phase6_other_{uuid.uuid4().hex}@example.com"
    password = "securepassword123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "user_id": uuid.UUID(me["id"]),
    }


def create_project(
    db: Session,
    user_id: uuid.UUID,
    *,
    filename: str = "song.mp3",
    status: str = "UPLOADED",
    created_at: datetime | None = None,
    vocals_url: str | None = None,
    instrumental_url: str | None = None,
) -> Project:
    project_id = uuid.uuid4()
    now = created_at or datetime.now(timezone.utc)
    project = Project(
        id=project_id,
        user_id=user_id,
        filename=filename,
        original_file_path=str(Path(settings.UPLOAD_DIR) / f"upload_{project_id}.mp3"),
        original_file_url=f"/api/v1/projects/file/upload_{project_id}.mp3",
        status=status,
        vocals_url=vocals_url,
        instrumental_url=instrumental_url,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_list_projects_owned_by_user_sorted_desc(
    client: TestClient,
    db: Session,
    user_auth: dict,
    other_user_auth: dict,
) -> None:
    older = create_project(
        db,
        user_auth["user_id"],
        filename="older.mp3",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    newer = create_project(
        db,
        user_auth["user_id"],
        filename="newer.mp3",
        created_at=datetime.now(timezone.utc),
    )
    create_project(db, other_user_auth["user_id"], filename="not-mine.mp3")

    response = client.get("/api/v1/projects", headers=user_auth["headers"])

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids == [str(newer.id), str(older.id)]


def test_get_project_enforces_ownership(
    client: TestClient,
    db: Session,
    user_auth: dict,
    other_user_auth: dict,
) -> None:
    project = create_project(db, user_auth["user_id"])

    own_response = client.get(f"/api/v1/projects/{project.id}", headers=user_auth["headers"])
    other_response = client.get(f"/api/v1/projects/{project.id}", headers=other_user_auth["headers"])

    assert own_response.status_code == 200
    assert own_response.json()["id"] == str(project.id)
    assert other_response.status_code == 404


def test_get_project_status(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(
        db,
        user_auth["user_id"],
        status="completed",
        vocals_url="/api/v1/projects/file/vocals/test.wav",
        instrumental_url="/api/v1/projects/file/instrumental/test.wav",
    )

    response = client.get(f"/api/v1/projects/{project.id}/status", headers=user_auth["headers"])

    assert response.status_code == 200
    assert response.json() == {
        "project_id": str(project.id),
        "status": "completed",
        "vocals_url": "/api/v1/projects/file/vocals/test.wav",
        "instrumental_url": "/api/v1/projects/file/instrumental/test.wav",
    }


def test_process_project_endpoint(client: TestClient, db: Session, user_auth: dict, monkeypatch) -> None:
    project = create_project(db, user_auth["user_id"])

    def mock_process_project(db_session: Session, project_id: uuid.UUID) -> Project:
        processed = db_session.get(Project, project_id)
        processed.status = "completed"
        processed.vocals_url = f"/api/v1/projects/file/vocals/{project_id}.wav"
        processed.instrumental_url = f"/api/v1/projects/file/instrumental/{project_id}.wav"
        db_session.commit()
        db_session.refresh(processed)
        return processed

    monkeypatch.setattr(projects_api.audio_service, "process_project", mock_process_project)

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=user_auth["headers"])

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["vocals_url"] == f"/api/v1/projects/file/vocals/{project.id}.wav"


def test_process_project_prevents_duplicate_processing(
    client: TestClient,
    db: Session,
    user_auth: dict,
) -> None:
    project = create_project(db, user_auth["user_id"], status="processing")

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=user_auth["headers"])

    assert response.status_code == 409


def test_process_project_enforces_ownership(
    client: TestClient,
    db: Session,
    user_auth: dict,
    other_user_auth: dict,
) -> None:
    project = create_project(db, user_auth["user_id"])

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=other_user_auth["headers"])

    assert response.status_code == 404


def test_download_vocals(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(db, user_auth["user_id"], status="completed")
    file_path = Path(settings.VOCALS_DIR) / f"{project.id}.wav"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"vocals data")

    response = client.get(f"/api/v1/downloads/vocals/{project.id}", headers=user_auth["headers"])

    assert response.status_code == 200
    assert response.content == b"vocals data"
    assert response.headers["content-type"].startswith("audio/wav")
    file_path.unlink(missing_ok=True)


def test_download_instrumental(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(db, user_auth["user_id"], status="completed")
    file_path = Path(settings.INSTRUMENTAL_DIR) / f"{project.id}.wav"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"instrumental data")

    response = client.get(f"/api/v1/downloads/instrumental/{project.id}", headers=user_auth["headers"])

    assert response.status_code == 200
    assert response.content == b"instrumental data"
    assert response.headers["content-type"].startswith("audio/wav")
    file_path.unlink(missing_ok=True)


def test_download_enforces_ownership(
    client: TestClient,
    db: Session,
    user_auth: dict,
    other_user_auth: dict,
) -> None:
    project = create_project(db, user_auth["user_id"], status="completed")
    file_path = Path(settings.VOCALS_DIR) / f"{project.id}.wav"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"vocals data")

    response = client.get(f"/api/v1/downloads/vocals/{project.id}", headers=other_user_auth["headers"])

    assert response.status_code == 404
    file_path.unlink(missing_ok=True)


def test_download_missing_file_returns_404(
    client: TestClient,
    db: Session,
    user_auth: dict,
) -> None:
    project = create_project(db, user_auth["user_id"], status="completed")
    file_path = Path(settings.VOCALS_DIR) / f"{project.id}.wav"
    file_path.unlink(missing_ok=True)

    response = client.get(f"/api/v1/downloads/vocals/{project.id}", headers=user_auth["headers"])

    assert response.status_code == 404