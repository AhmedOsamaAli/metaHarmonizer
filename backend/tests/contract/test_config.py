from fastapi.testclient import TestClient

from app.main import app


def test_frontend_config_path_returns_feature_flags():
    response = TestClient(app).get("/api/v1/config")

    assert response.status_code == 200
    assert isinstance(response.json()["llm_enabled"], bool)


def test_redoc_uses_pinned_bundle_without_google_fonts():
    response = TestClient(app).get("/redoc")

    assert response.status_code == 200
    assert "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js" in response.text
    assert "fonts.googleapis.com" not in response.text