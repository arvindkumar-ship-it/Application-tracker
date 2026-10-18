"""Phase 1 checks only. Live Docker/database and later-phase flows remain gated."""
import os
import secrets
import unittest
from unittest.mock import patch
from app.security import hash_password, verify_password, create_session, verify_session, valid_password_hash

PASSWORD = secrets.token_urlsafe(24)
ENCODED = hash_password(PASSWORD)
# Test process only; never reuse these credentials in a running portal.
os.environ.update(DATABASE_URL="postgresql+asyncpg://portal:portal@localhost:5432/portal", REDIS_URL="redis://localhost:6379/0", SESSION_SECRET=secrets.token_urlsafe(40), APP_PASSWORD_HASH=ENCODED)
from fastapi.testclient import TestClient
from app.main import app
from app.models import metadata


class FakeRedis:
    def __init__(self): self.failures = 0
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def get(self, key): return str(self.failures)
    async def eval(self, *args): self.failures += 1
    async def delete(self, key): self.failures = 0


class FoundationChecks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_all_tables_registered(self):
        self.assertEqual(set(metadata.tables), {"profile", "education", "experience", "project", "project_tech", "achievement", "publication", "certification", "skill", "resume_variant", "fact", "intake", "job", "master_row", "status_history", "jd_analysis", "tailored_resume", "sheet_sync_log", "app_setting"})

    def test_password_and_signed_session(self):
        self.assertTrue(valid_password_hash(ENCODED))
        self.assertTrue(verify_password(PASSWORD, ENCODED))
        self.assertFalse(verify_password("wrong password", ENCODED))
        self.assertFalse(valid_password_hash("bad"))
        token = create_session(os.environ["SESSION_SECRET"])
        self.assertTrue(verify_session(token, os.environ["SESSION_SECRET"]))
        self.assertFalse(verify_session(token + "x", os.environ["SESSION_SECRET"]))
        self.assertFalse(verify_session(token, "other-secret"))

    def test_distinct_enum_sets_do_not_collide(self):
        vault_type = metadata.tables["experience"].c.employment_type.type
        job_type = metadata.tables["job"].c.employment_type.type
        self.assertNotEqual(vault_type.name, job_type.name)
        self.assertIn("volunteer", vault_type.enums)
        self.assertNotIn("volunteer", job_type.enums)
        self.assertIn("unspecified", job_type.enums)

    def test_auth_cookie_login_and_logout(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        with patch("app.api.auth.Redis.from_url", return_value=FakeRedis()):
            self.assertEqual(self.client.post("/api/auth/login", json={"password":""}).status_code, 422)
            self.assertEqual(self.client.post("/api/auth/login", json={"password":"wrong"}).status_code, 401)
            response = self.client.post("/api/auth/login", json={"password":PASSWORD})
            self.assertEqual(response.status_code, 200)
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            self.assertIn("SameSite=lax", response.headers["set-cookie"])
            self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
            self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_rate_limit(self):
        with patch("app.api.auth.Redis.from_url", return_value=FakeRedis()):
            for _ in range(5):
                self.assertEqual(self.client.post("/api/auth/login", json={"password":"wrong"}).status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login", json={"password":PASSWORD}).status_code, 429)

    def test_redis_failure_fails_closed(self):
        with patch("app.api.auth.Redis.from_url", side_effect=ConnectionError()):
            self.assertEqual(self.client.post("/api/auth/login", json={"password":PASSWORD}).status_code, 503)

    def test_origin_guard_and_standard_error(self):
        response = self.client.post("/api/auth/login", headers={"Origin":"https://untrusted.invalid"}, json={"password":PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.json()), {"code", "message", "details"})


if __name__ == "__main__":
    unittest.main()
