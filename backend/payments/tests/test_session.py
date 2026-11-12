import unittest
from unittest.mock import patch
from fastapi import Request
from fastapi.testclient import TestClient
from backend.main import app
from backend.session import new_cookie, session_for_cookie


class SessionTests(unittest.TestCase):
    def test_cookie_is_stable_and_bound_to_secret(self):
        secret = "a" * 32
        cookie = new_cookie(secret)
        identity = session_for_cookie(cookie, secret)
        self.assertTrue(identity.startswith("s_"))
        self.assertEqual(identity, session_for_cookie(cookie, secret))
        self.assertIsNone(session_for_cookie(cookie, "b" * 32))
        self.assertIsNone(session_for_cookie(cookie[:-1] + ("0" if cookie[-1] != "0" else "1"), secret))

    def test_different_sessions_have_different_identities(self):
        secret = "a" * 32
        self.assertNotEqual(session_for_cookie(new_cookie(secret), secret), session_for_cookie(new_cookie(secret), secret))

    def test_middleware_uses_same_identity_on_refresh(self):
        @app.get("/_session_test")
        def show_session(request: Request):
            return {"session": request.state.session_id}

        with patch.dict("os.environ", {"B4_ENABLED": "true", "SESSION_SECRET": "a" * 40}, clear=True):
            client = TestClient(app)
            first = client.get("/_session_test")
            second = client.get("/_session_test")
            stranger = TestClient(app).get("/_session_test")
        self.assertEqual(first.json(), second.json())
        self.assertNotEqual(first.json(), stranger.json())
        self.assertIn("HttpOnly", first.headers["set-cookie"])
