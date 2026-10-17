"""极简密码登录：HMAC 签名令牌 + 内存限流。不依赖第三方库。

环境变量：
  FP_APP_PASSWORD  登录密码。未设置时不启用登录（仅适合本机开发）。
  FP_SECRET_KEY    令牌签名密钥。未设置时每次启动随机生成（重启后需重新登录）。
  FP_TOKEN_DAYS    令牌有效天数，默认 30。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque

_RANDOM_KEY = secrets.token_urlsafe(32)
_attempts: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
LOGIN_LIMIT, LOGIN_WINDOW = 5, 60.0


def auth_enabled() -> bool:
    return bool(os.environ.get("FP_APP_PASSWORD"))


def _key() -> bytes:
    return (os.environ.get("FP_SECRET_KEY") or _RANDOM_KEY).encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def check_password(pw: str) -> bool:
    expected = os.environ.get("FP_APP_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(pw.encode("utf-8"), expected.encode("utf-8"))


def make_token() -> tuple[str, int]:
    exp = int(time.time() + float(os.environ.get("FP_TOKEN_DAYS", "30")) * 86400)
    body = _b64(json.dumps({"exp": exp, "n": secrets.token_hex(4)}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", exp


def verify_token(token: str) -> bool:
    try:
        body, sig = token.split(".", 1)
        good = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return False
        return json.loads(_unb64(body))["exp"] > time.time()
    except Exception:
        return False


def client_ip(headers, fallback: str) -> str:
    """优先 CF-Connecting-IP（Cloudflare），其次 X-Forwarded-For 的第一个地址。"""
    ip = headers.get("cf-connecting-ip")
    if not ip and headers.get("x-forwarded-for"):
        ip = headers["x-forwarded-for"].split(",")[0]
    return (ip or fallback or "unknown").strip()


def rate_limited(ip: str) -> bool:
    """每个 IP 每 60 秒最多 5 次登录尝试。超过返回 True。"""
    now = time.time()
    with _lock:
        q = _attempts[ip]
        while q and now - q[0] > LOGIN_WINDOW:
            q.popleft()
        if len(q) >= LOGIN_LIMIT:
            return True
        q.append(now)
        if len(_attempts) > 10000:  # 防止内存无限增长
            for k in [k for k, v in _attempts.items() if not v]:
                del _attempts[k]
        return False


def reset_limits() -> None:
    with _lock:
        _attempts.clear()
