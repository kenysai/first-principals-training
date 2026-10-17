#!/usr/bin/env bash
# 本地启动：./run.sh  （端口可用 PORT 覆盖）
cd "$(dirname "$0")"
exec "${PYTHON:-python3}" -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
