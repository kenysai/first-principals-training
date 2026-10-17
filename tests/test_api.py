"""离线 API 测试：模拟 Jev + 模拟 LLM，临时数据库。运行：python -m unittest -v tests/test_api.py"""
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
os.environ.update({"FP_DB_PATH": str(Path(tempfile.mkdtemp()) / "t.db"), "TYPESAFE_MOCK": "1", "FP_LLM_MOCK": "1"})

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.c.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.c.__exit__(None, None, None)

    def test_01_config_and_demo(self):
        cfg = self.c.get("/api/config").json()
        self.assertEqual(cfg["jev"], "mock")
        self.assertTrue(cfg["llm_enabled"])
        self.assertNotIn("key", str(cfg).lower().replace("ai_steps", ""))
        ps = self.c.get("/api/problems").json()
        self.assertTrue(any(p["is_demo"] for p in ps))
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_02_flow(self):
        c = self.c
        p = c.post("/api/problems", json={"title": "周报每周要花半天", "background": "数据来自 3 个系统", "domain": "工作", "importance": "高"}).json()
        pid = p["id"]
        self.assertEqual(p["status"], "提出")
        data = {"define": {"problem_restated": "缩短周报时间", "goal": "1 小时内"},
                "decompose": {"assumptions": [{"statement": "数据来自 3 个系统", "type": ""},
                                              {"statement": "经理通常只看结论", "type": "假设"}],
                              "five_whys": [{"why": "为什么慢？", "answer": "手工导出", "type": "事实"}]}}
        r = c.put(f"/api/problems/{pid}", json={"data": data, "status": "拆解"}).json()
        self.assertEqual(r["status"], "拆解")
        r = c.post(f"/api/problems/{pid}/jev/classify").json()
        a = r["problem"]["data"]["decompose"]["assumptions"]
        self.assertIn(a[0]["jev"]["type"], ("事实", "假设", "惯例"))
        self.assertEqual(a[0]["type"], a[0]["jev"]["type"])      # 空标注由 Jev 填入
        self.assertEqual(a[1]["type"], "假设")                     # 用户标注不被覆盖
        r = c.post(f"/api/problems/{pid}/jev/has-data").json()
        self.assertIn("confidence", r["problem"]["data"]["decompose"]["assumptions"][0]["jev_data"])
        r = c.post(f"/api/problems/{pid}/jev/quick-check").json()
        self.assertIn("jev", r["problem"]["data"]["quick"]["costly"])
        self.assertIn("seconds", r["stats"])
        for step in ("define", "decompose", "rebuild", "premortem", "experiment", "review"):
            s = c.post(f"/api/problems/{pid}/ai/{step}")
            self.assertEqual(s.status_code, 200, s.text)
            self.assertTrue(s.json()["suggestion"])
        self.assertEqual(c.post(f"/api/problems/{pid}/ai/quick").status_code, 400)
        md = c.get(f"/api/problems/{pid}/export.md")
        self.assertEqual(md.status_code, 200)
        self.assertIn("attachment", md.headers["content-disposition"])
        self.assertIn("## 第3步 拆到基本事实", md.text)
        self.assertIn("数据来自 3 个系统", md.text)
        js = c.get(f"/api/problems/{pid}/export.json").json()
        self.assertEqual(js["id"], pid)
        self.assertEqual(c.put(f"/api/problems/{pid}", json={"status": "乱写"}).status_code, 422)
        self.assertEqual(len(c.get("/api/problems?status=拆解").json()), 1)
        self.assertEqual(c.delete(f"/api/problems/{pid}").json(), {"ok": True})
        self.assertEqual(c.get(f"/api/problems/{pid}").status_code, 404)

    def test_03_demo_export_and_delete(self):
        demo = [p for p in self.c.get("/api/problems").json() if p["is_demo"]][0]
        md = self.c.get(f"/api/problems/{demo['id']}/export.md?download=0").text
        self.assertIn("⚠待确认", md)
        self.c.delete(f"/api/problems/{demo['id']}")
        from app import db, logic
        logic.seed_if_needed(db)  # 删除后不会自动重新出现
        self.assertFalse(any(p["is_demo"] for p in self.c.get("/api/problems").json()))
        self.assertTrue(self.c.post("/api/demo").json()["is_demo"])

    def test_04_jev_off(self):
        os.environ.pop("TYPESAFE_MOCK")
        try:
            pid = self.c.post("/api/problems", json={"title": "x"}).json()["id"]
            r = self.c.post(f"/api/problems/{pid}/jev/classify")
            self.assertEqual(r.status_code, 400)
        finally:
            os.environ["TYPESAFE_MOCK"] = "1"


if __name__ == "__main__":
    unittest.main()
