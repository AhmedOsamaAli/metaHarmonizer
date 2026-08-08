from __future__ import annotations

import jwt
import pytest

from app.core.security import create_access_token, decode_token
from app.core.settings import settings


def test_jwt_rotation_rejects_old_tokens_and_signs_new_tokens(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "old-rotation-secret-that-is-at-least-32-bytes")
    old_token = create_access_token(user_id=1, role="curator", email="rotation@example.com")

    monkeypatch.setattr(settings, "jwt_secret", "new-rotation-secret-that-is-at-least-32-bytes")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(old_token)

    new_token = create_access_token(user_id=1, role="curator", email="rotation@example.com")
    assert decode_token(new_token)["sub"] == "1"