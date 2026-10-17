"""FastAPI 后端。所有 API key 只在服务器端读取，绝不返回给前端。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os  # noqa: E402

from fastapi import Body, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app import auth, db, logic  # noqa: E402
from fp_core.judge import JevError  # noqa: E402

app = FastAPI(title="第一性原理问题拆解器")
STATIC = Path(__file__).resolve().parent / "static"


PUBLIC_API = {"/api/login", "/api/health"}


@app.middleware("http")
async def require_auth(request: Request, call_next):
    """除登录和健康检查外，所有 /api/* 都需要 Authorization: Bearer <token>。"""
    path = request.url.path
    if (path.startswith("/api/") and path not in PUBLIC_API and request.method != "OPTIONS" and auth.auth_enabled()):
        h = request.headers.get("authorization", "")
        if not (h.lower().startswith("bearer ") and auth.verify_token(h[7:].strip())):
            return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


_origins = [o.strip().rstrip("/") for o in os.environ.get("FP_ALLOWED_ORIGINS", "https://kenysai.github.io").split(",") if o.strip()]
# CORS 放在最外层，这样 401 响应也带上 CORS 头，前端才能读到并跳转登录
app.add_middleware(CORSMiddleware, allow_origins=_origins,
                   allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"],
                   max_age=86400)


@app.post("/api/login")
def login(request: Request, body: dict = Body(...)):
    if not auth.auth_enabled():
        return {"token": "", "expires": 0, "auth": False}
    ip = auth.client_ip(request.headers, request.client.host if request.client else "")
    if auth.rate_limited(ip):
        raise HTTPException(429, "尝试次数太多，请 1 分钟后再试")
    if not auth.check_password(str(body.get("password", ""))):
        raise HTTPException(401, "密码不对")
    token, exp = auth.make_token()
    return {"token": token, "expires": exp, "auth": True}


@app.get("/api/health")
def api_health():
    return {"ok": True, "auth": auth.auth_enabled()}


@app.on_event("startup")
def _startup() -> None:
    db.init()
    logic.seed_if_needed(db)


def _get(pid: int) -> dict:
    p = db.get(pid)
    if not p:
        raise HTTPException(404, "问题不存在")
    return p


@app.get("/api/config")
def config():
    llm = logic.llm_status()
    return {"jev": logic.jev_mode(), "threshold": logic.THRESHOLD, "statuses": db.STATUSES,
            "llm_enabled": llm["enabled"], "llm_name": llm["name"], "llm_reason": llm["reason"],
            "ai_steps": sorted(logic.AI_STEPS)}


@app.get("/api/problems")
def list_problems(status: str | None = None):
    return db.list_problems(status)


@app.post("/api/problems")
def create_problem(p: dict = Body(...)):
    if not (p.get("title") or "").strip():
        raise HTTPException(422, "请填写问题")
    if p.get("status") and p["status"] not in db.STATUSES:
        raise HTTPException(422, "状态不合法")
    p.setdefault("data", {})
    return db.create(p)


@app.get("/api/problems/{pid}")
def get_problem(pid: int):
    return _get(pid)


@app.put("/api/problems/{pid}")
def update_problem(pid: int, p: dict = Body(...)):
    _get(pid)
    if "status" in p and p["status"] not in db.STATUSES:
        raise HTTPException(422, "状态不合法")
    if "title" in p and not (p["title"] or "").strip():
        raise HTTPException(422, "问题不能为空")
    return db.update(pid, p)


@app.delete("/api/problems/{pid}")
def delete_problem(pid: int):
    _get(pid)
    db.delete(pid)
    return {"ok": True}


@app.post("/api/demo")
def restore_demo():
    return db.create(logic.demo_problem(), is_demo=True)


def _jev(pid: int, fn):
    if logic.jev_mode() == "off":
        raise HTTPException(400, "未配置 TYPESAFE_API_KEY，Jev 辅助不可用")
    p = _get(pid)
    try:
        p, stats = fn(p)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except JevError as e:
        raise HTTPException(502, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"Jev 调用失败：{e}")
    return {"problem": db.update(pid, {"data": p["data"]}), "stats": stats}


@app.post("/api/problems/{pid}/jev/classify")
def jev_classify(pid: int):
    return _jev(pid, logic.jev_classify)


@app.post("/api/problems/{pid}/jev/has-data")
def jev_has_data(pid: int):
    return _jev(pid, logic.jev_has_data)


@app.post("/api/problems/{pid}/jev/quick-check")
def jev_quick(pid: int):
    return _jev(pid, logic.jev_quick)


@app.post("/api/problems/{pid}/ai/{step}")
def ai_suggest(pid: int, step: str):
    p = _get(pid)
    try:
        sug, usage = logic.llm_suggest(p, step)
        return {"suggestion": sug, "usage": usage}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # 模型返回不合法等
        raise HTTPException(502, f"AI 建议失败：{str(e)[:300]}")


def _fname(p: dict, ext: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", p["title"]).strip("-")[:30] or "problem"
    return f"{p['id']}-{slug}.{ext}"


def _download(content: str, name: str, media: str) -> Response:
    return Response(content, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename=\"export.{name.rsplit('.', 1)[1]}\"; filename*=UTF-8''{quote(name)}"})


@app.get("/api/problems/{pid}/export.md")
def export_md(pid: int, download: int = 1):
    p = _get(pid)
    md = logic.export_markdown(p)
    if not download:
        return PlainTextResponse(md)
    return _download(md, _fname(p, "md"), "text/markdown; charset=utf-8")


@app.get("/api/problems/{pid}/export.json")
def export_json(pid: int):
    p = _get(pid)
    return _download(json.dumps(p, ensure_ascii=False, indent=2), _fname(p, "json"), "application/json; charset=utf-8")


@app.get("/healthz")
def health():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
