import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import projects as projects_api
from app.core.config import settings
from app.models.job import Job
from app.models.project import Project


@pytest.fixture
def user_auth(client: TestClient) -> dict:
    email = f"phase7_{uuid.uuid4().hex}@example.com"
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
    email = f"phase7_other_{uuid.uuid4().hex}@example.com"
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
        status="COMPLETED",
        vocals_url="/api/v1/projects/file/vocals/test.wav",
        instrumental_url="/api/v1/projects/file/instrumental/test.wav",
    )

    response = client.get(f"/api/v1/projects/{project.id}/status", headers=user_auth["headers"])

    assert response.status_code == 200
    assert response.json() == {
        "project_id": str(project.id),
        "status": "COMPLETED",
        "vocals_url": "/api/v1/projects/file/vocals/test.wav",
        "instrumental_url": "/api/v1/projects/file/instrumental/test.wav",
    }


def test_start_processing_queues_background_task(
    client: TestClient,
    db: Session,
    user_auth: dict,
    monkeypatch,
) -> None:
    project = create_project(db, user_auth["user_id"])
    queued = []

    def fake_background(project_id: uuid.UUID, job_id: uuid.UUID) -> None:
        queued.append((project_id, job_id))

    monkeypatch.setattr(projects_api, "_run_process_project_background", fake_background)

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=user_auth["headers"])

    assert response.status_code == 202
    assert response.json()["status"] == "PENDING"
    assert queued and queued[0][0] == project.id

    db.refresh(project)
    assert project.status == "PENDING"
    job = db.get(Job, queued[0][1])
    assert job is not None
    assert job.status == "PENDING"
    assert job.user_id == user_auth["user_id"]


def test_processing_invalid_project_returns_404(client: TestClient, user_auth: dict) -> None:
    response = client.post(f"/api/v1/projects/{uuid.uuid4()}/process", headers=user_auth["headers"])

    assert response.status_code == 404


@pytest.mark.parametrize("project_status", ["PENDING", "PROCESSING"])
def test_duplicate_processing_returns_400(
    client: TestClient,
    db: Session,
    user_auth: dict,
    project_status: str,
) -> None:
    project = create_project(db, user_auth["user_id"], status=project_status)

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=user_auth["headers"])

    assert response.status_code == 400


def test_process_project_unauthorized_returns_401(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(db, user_auth["user_id"])

    response = client.post(f"/api/v1/projects/{project.id}/process")

    assert response.status_code == 401


def test_process_project_forbidden_for_other_user(
    client: TestClient,
    db: Session,
    user_auth: dict,
    other_user_auth: dict,
) -> None:
    project = create_project(db, user_auth["user_id"])

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=other_user_auth["headers"])

    assert response.status_code == 403


def test_completed_project_cannot_be_processed(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(db, user_auth["user_id"], status="COMPLETED")

    response = client.post(f"/api/v1/projects/{project.id}/process", headers=user_auth["headers"])

    assert response.status_code == 400


def test_background_task_execution_invokes_audio_service(db: Session, monkeypatch) -> None:
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    calls = []

    class SessionFactory:
        def __call__(self) -> Session:
            return db

    def fake_process_project(db_session: Session, queued_project_id: uuid.UUID, queued_job_id: uuid.UUID) -> None:
        calls.append((db_session, queued_project_id, queued_job_id))

    monkeypatch.setattr(projects_api, "SessionLocal", SessionFactory())
    monkeypatch.setattr(projects_api.audio_service, "process_project", fake_process_project)

    projects_api._run_process_project_background(project_id, job_id)

    assert calls == [(db, project_id, job_id)]


def test_download_vocals(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(db, user_auth["user_id"], status="COMPLETED")
    file_path = Path(settings.VOCALS_DIR) / f"{project.id}.wav"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"vocals data")

    response = client.get(f"/api/v1/downloads/vocals/{project.id}", headers=user_auth["headers"])

    assert response.status_code == 200
    assert response.content == b"vocals data"
    assert response.headers["content-type"].startswith("audio/wav")
    file_path.unlink(missing_ok=True)


def test_download_instrumental(client: TestClient, db: Session, user_auth: dict) -> None:
    project = create_project(db, user_auth["user_id"], status="COMPLETED")
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
    project = create_project(db, user_auth["user_id"], status="COMPLETED")
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
    project = create_project(db, user_auth["user_id"], status="COMPLETED")
    file_path = Path(settings.VOCALS_DIR) / f"{project.id}.wav"
    file_path.unlink(missing_ok=True)

    response = client.get(f"/api/v1/downloads/vocals/{project.id}", headers=user_auth["headers"])

    assert response.status_code == 404
