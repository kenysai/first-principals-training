"""SQLite 存储：每个问题一行，步骤内容放在 data(JSON) 里。"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("FP_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "fp.db"))
_lock = threading.Lock()

STATUSES = ["提出", "拆解", "解决", "复盘", "完成"]


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect():
    """打开连接，成功则提交，最后总是关闭。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    with _lock, connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            background TEXT DEFAULT '',
            status TEXT DEFAULT '提出',
            domain TEXT DEFAULT '个人',
            importance TEXT DEFAULT '中',
            is_demo INTEGER DEFAULT 0,
            deadline TEXT DEFAULT '',
            review_date TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        """)


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"] or "{}")
    d["is_demo"] = bool(d["is_demo"])
    return d


FIELDS = ["title", "background", "status", "domain", "importance", "deadline", "review_date"]


def list_problems(status: str | None = None) -> list[dict]:
    with connect() as con:
        if status:
            rows = con.execute("SELECT * FROM problems WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM problems ORDER BY updated_at DESC").fetchall()
    return [_row(r) for r in rows]


def get(pid: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    return _row(r) if r else None


def create(p: dict, is_demo: bool = False) -> dict:
    t = now()
    with _lock, connect() as con:
        cur = con.execute(
            "INSERT INTO problems (title, background, status, domain, importance, is_demo, deadline, review_date, data, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (p["title"], p.get("background", ""), p.get("status", "提出"), p.get("domain", "个人"), p.get("importance", "中"),
             int(is_demo), p.get("deadline", ""), p.get("review_date", ""),
             json.dumps(p.get("data", {}), ensure_ascii=False), t, t))
        pid = cur.lastrowid
    return get(pid)


def update(pid: int, p: dict) -> dict | None:
    sets, vals = [], []
    for f in FIELDS:
        if f in p:
            sets.append(f"{f}=?")
            vals.append(p[f])
    if "data" in p:
        sets.append("data=?")
        vals.append(json.dumps(p["data"], ensure_ascii=False))
    sets.append("updated_at=?")
    vals.append(now())
    with _lock, connect() as con:
        con.execute(f"UPDATE problems SET {', '.join(sets)} WHERE id=?", (*vals, pid))
    return get(pid)


def delete(pid: int) -> None:
    with _lock, connect() as con:
        con.execute("DELETE FROM problems WHERE id=?", (pid,))


def meta_get(key: str) -> str | None:
    with connect() as con:
        r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def meta_set(key: str, value: str) -> None:
    with _lock, connect() as con:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
