from fastapi.testclient import TestClient

from app.main import app


def test_frontend_config_path_returns_feature_flags():
    response = TestClient(app).get("/api/v1/config")

    assert response.status_code == 200
    assert isinstance(response.json()["llm_enabled"], bool)


def test_redoc_is_not_exposed():
    response = TestClient(app).get("/redoc")

    assert response.status_code == 404