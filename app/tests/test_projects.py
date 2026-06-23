import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from pathlib import Path

from app.models.project import Project
from app.utils import file_utils

@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """Fixture to register and login a test user, returning auth headers."""
    email = "uploader@example.com"
    password = "securepassword123"
    # Register
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    # Login
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_upload_file_success_mp3(client: TestClient, auth_headers: dict, db: Session) -> None:
    # Simulate an MP3 upload
    file_content = b"fake mp3 audio data"
    file_name = "test_song.mp3"
    files = {"file": (file_name, io.BytesIO(file_content), "audio/mpeg")}
    
    response = client.post("/api/v1/projects/upload", files=files, headers=auth_headers)
    assert response.status_code == 201
    
    data = response.json()
    assert data["message"] == "File uploaded successfully"
    assert "project" in data
    
    project_data = data["project"]
    assert project_data["filename"] == file_name
    assert project_data["status"] == "UPLOADED"
    assert "id" in project_data
    assert "original_file_path" in project_data
    assert "original_file_url" in project_data
    
    # Verify file was written physically
    saved_path = Path(project_data["original_file_path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == file_content
    
    # Cleanup file
    file_utils.delete_physical_file(saved_path)

def test_upload_file_success_wav(client: TestClient, auth_headers: dict) -> None:
    # Simulate a WAV upload
    file_content = b"fake wav audio data"
    file_name = "test_audio.wav"
    files = {"file": (file_name, io.BytesIO(file_content), "audio/wav")}
    
    response = client.post("/api/v1/projects/upload", files=files, headers=auth_headers)
    assert response.status_code == 201
    
    project_data = response.json()["project"]
    saved_path = Path(project_data["original_file_path"])
    assert saved_path.exists()
    
    # Cleanup
    file_utils.delete_physical_file(saved_path)

def test_upload_file_invalid_extension(client: TestClient, auth_headers: dict) -> None:
    # Simulate uploading a txt file
    file_content = b"plain text data"
    file_name = "malicious_script.sh"
    files = {"file": (file_name, io.BytesIO(file_content), "text/plain")}
    
    response = client.post("/api/v1/projects/upload", files=files, headers=auth_headers)
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]

def test_upload_file_invalid_mime_mismatch(client: TestClient, auth_headers: dict) -> None:
    # MP3 extension with plain text MIME type
    file_content = b"some data"
    file_name = "song.mp3"
    files = {"file": (file_name, io.BytesIO(file_content), "text/plain")}
    
    response = client.post("/api/v1/projects/upload", files=files, headers=auth_headers)
    assert response.status_code == 400
    assert "MIME type" in response.json()["detail"]

def test_upload_file_unauthorized(client: TestClient) -> None:
    files = {"file": ("song.mp3", io.BytesIO(b"data"), "audio/mpeg")}
    response = client.post("/api/v1/projects/upload", files=files)
    assert response.status_code == 401

def test_upload_file_size_exceeded(client: TestClient, auth_headers: dict, monkeypatch) -> None:
    # Mock file size validation to trigger limit
    # Temporarily set max size to 10 bytes for testing
    monkeypatch.setattr(file_utils, "MAX_FILE_SIZE", 10)
    
    file_content = b"fake audio data that exceeds ten bytes limit"
    files = {"file": ("overlimit.mp3", io.BytesIO(file_content), "audio/mpeg")}
    
    response = client.post("/api/v1/projects/upload", files=files, headers=auth_headers)
    assert response.status_code == 400
    assert "exceeds the maximum limit" in response.json()["detail"]

def test_upload_file_path_traversal_sanitization(client: TestClient, auth_headers: dict) -> None:
    # Simulating directory traversal filename
    file_content = b"fake wav audio data"
    file_name = "../../../test_traversal.wav"
    files = {"file": (file_name, io.BytesIO(file_content), "audio/wav")}
    
    response = client.post("/api/v1/projects/upload", files=files, headers=auth_headers)
    assert response.status_code == 201
    
    project_data = response.json()["project"]
    # The actual saved filename path shouldn't contain relative path segments
    saved_path = Path(project_data["original_file_path"])
    assert saved_path.exists()
    assert ".." not in saved_path.name
    
    # Cleanup
    file_utils.delete_physical_file(saved_path)
