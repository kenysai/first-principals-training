"""登录、令牌、限流和 CORS 测试（离线）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for k in list(os.environ):
    if k.startswith(("TYPESAFE_", "LLM_", "FP_APP_PASSWORD", "FP_SECRET_KEY", "FP_ALLOWED_ORIGINS")):
        del os.environ[k]
os.environ.setdefault("FP_DB_PATH", str(Path(tempfile.mkdtemp()) / "a.db"))
os.environ.setdefault("TYPESAFE_MOCK", "1")
os.environ.setdefault("FP_LLM_MOCK", "1")

from fastapi.testclient import TestClient  # noqa: E402

from app import auth  # noqa: E402
from app.main import app  # noqa: E402

PW = "test-密码-123"


class TestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.c.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.c.__exit__(None, None, None)

    def setUp(self):
        os.environ["FP_APP_PASSWORD"] = PW
        os.environ["FP_SECRET_KEY"] = "unit-test-secret"
        auth.reset_limits()

    def tearDown(self):
        os.environ.pop("FP_APP_PASSWORD", None)
        os.environ.pop("FP_SECRET_KEY", None)
        auth.reset_limits()

    def login(self, pw=PW, ip="1.2.3.4"):
        return self.c.post("/api/login", json={"password": pw}, headers={"CF-Connecting-IP": ip})

    def test_public_and_protected(self):
        self.assertEqual(self.c.get("/api/health").json(), {"ok": True, "auth": True})
        self.assertEqual(self.c.get("/").status_code, 200)            # 前端页面本身公开
        self.assertEqual(self.c.get("/static/config.js").status_code, 200)
        for m, path in [("GET", "/api/config"), ("GET", "/api/problems"), ("POST", "/api/problems"), ("GET", "/api/problems/1/export.md")]:
            r = self.c.request(m, path, json={"title": "x"} if m == "POST" else None)
            self.assertEqual(r.status_code, 401, path)
        self.assertEqual(self.c.get("/api/problems", headers={"Authorization": "Bearer garbage"}).status_code, 401)

    def test_login_flow(self):
        self.assertEqual(self.login("wrong").status_code, 401)
        r = self.login()
        self.assertEqual(r.status_code, 200)
        tok = r.json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        self.assertEqual(self.c.get("/api/problems", headers=h).status_code, 200)
        pid = self.c.post("/api/problems", json={"title": "登录后创建"}, headers=h).json()["id"]
        self.assertEqual(self.c.get(f"/api/problems/{pid}/export.md", headers=h).status_code, 200)
        # 换密钥后旧令牌失效
        os.environ["FP_SECRET_KEY"] = "rotated"
        self.assertEqual(self.c.get("/api/problems", headers=h).status_code, 401)

    def test_expired_and_tampered(self):
        os.environ["FP_TOKEN_DAYS"] = "-1"
        try:
            tok = self.login().json()["token"]
        finally:
            os.environ.pop("FP_TOKEN_DAYS")
        self.assertFalse(auth.verify_token(tok))
        good = self.login(ip="5.5.5.5").json()["token"]
        body, sig = good.split(".")
        self.assertFalse(auth.verify_token(body + "x." + sig))
        self.assertTrue(auth.verify_token(good))

    def test_rate_limit_per_ip(self):
        codes = [self.login("wrong", ip="9.9.9.9").status_code for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)
        self.assertEqual(self.login("wrong", ip="9.9.9.9").status_code, 429)
        self.assertEqual(self.login(ip="8.8.8.8").status_code, 200)       # 其他 IP 不受影响
        r = self.c.post("/api/login", json={"password": "x"}, headers={"X-Forwarded-For": "7.7.7.7, 10.0.0.1"})
        self.assertEqual(auth.client_ip({"x-forwarded-for": "7.7.7.7, 10.0.0.1"}, "127.0.0.1"), "7.7.7.7")
        self.assertEqual(r.status_code, 401)

    def test_cors(self):
        pre = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
        r = self.c.options("/api/problems", headers={"Origin": "https://kenysai.github.io", **pre})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("access-control-allow-origin"), "https://kenysai.github.io")
        self.assertIn("authorization", r.headers.get("access-control-allow-headers", "").lower())
        r = self.c.options("/api/problems", headers={"Origin": "http://localhost:5500", **pre})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5500")
        r = self.c.options("/api/problems", headers={"Origin": "https://evil.example.com", **pre})
        self.assertNotEqual(r.headers.get("access-control-allow-origin"), "https://evil.example.com")
        r = self.c.get("/api/problems", headers={"Origin": "https://kenysai.github.io"})   # 401 也要带 CORS 头
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers.get("access-control-allow-origin"), "https://kenysai.github.io")

    def test_auth_disabled_without_password(self):
        os.environ.pop("FP_APP_PASSWORD")
        self.assertEqual(self.c.get("/api/problems").status_code, 200)
        self.assertEqual(self.c.get("/api/health").json()["auth"], False)


if __name__ == "__main__":
    unittest.main()
