import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.security import verify_password
from app.models.user import User

def test_register_user_success(client: TestClient) -> None:
    payload = {
        "email": "test@example.com",
        "password": "strongpassword123"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    
    data = response.json()
    assert "id" in data
    assert data["email"] == payload["email"]
    assert "password_hash" not in data
    assert "hashed_password" not in data
    assert data["is_active"] is True

def test_register_user_duplicate_email(client: TestClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "password": "password123"
    }
    # Register once
    response1 = client.post("/api/v1/auth/register", json=payload)
    assert response1.status_code == 201
    
    # Register second time
    response2 = client.post("/api/v1/auth/register", json=payload)
    assert response2.status_code == 400
    assert response2.json()["detail"] == "Email already registered"

def test_login_success(client: TestClient) -> None:
    # 1. Register a user
    register_payload = {
        "email": "login@example.com",
        "password": "secretpassword"
    }
    client.post("/api/v1/auth/register", json=register_payload)
    
    # 2. Login
    login_payload = {
        "email": "login@example.com",
        "password": "secretpassword"
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_incorrect_password(client: TestClient) -> None:
    # 1. Register a user
    register_payload = {
        "email": "wrongpass@example.com",
        "password": "correctpassword"
    }
    client.post("/api/v1/auth/register", json=register_payload)
    
    # 2. Try to login with wrong password
    login_payload = {
        "email": "wrongpass@example.com",
        "password": "wrongpassword"
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_login_non_existent_user(client: TestClient) -> None:
    login_payload = {
        "email": "nonexistent@example.com",
        "password": "somepassword"
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_get_me_success(client: TestClient) -> None:
    # 1. Register
    email = "me@example.com"
    password = "mypassword"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    
    # 2. Login to get token
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    
    # 3. Request /me
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["email"] == email
    assert "id" in data
    assert "password_hash" not in data

def test_get_me_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

def test_get_me_invalid_token(client: TestClient) -> None:
    headers = {"Authorization": "Bearer invalid_token_value"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 403
