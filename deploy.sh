#!/usr/bin/env bash
# 部署/更新后端到自己的服务器（无需 sudo、无需 docker）。
#
# 用法：
#   ./deploy.sh              同步代码 → 安装依赖 → 安装/重启 systemd --user 服务 → 健康检查
#   ./deploy.sh --init-env   另外把本机环境变量里的密钥写成服务器上的 .env（chmod 600）
#                            需要本机已设置：LLM_API_KEY TYPESAFE_API_KEY FP_APP_PASSWORD
#                            FP_SECRET_KEY 不存在时在服务器上随机生成；已存在则保留原值（避免所有人被登出）
#
# 可用环境变量覆盖：FP_SSH_KEY FP_SSH_PORT FP_SSH_TARGET FP_REMOTE_DIR FP_PORT
#   FP_PYTHON  创建虚拟环境用的 Python（默认服务器的 /usr/bin/python3；依赖装不上时自动改用 uv 管理的 3.12）
# 例：FP_SSH_TARGET=grok@1.2.3.4 ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

KEY=${FP_SSH_KEY:-$HOME/.ssh/kenny_server_ed25519}
PORT=${FP_SSH_PORT:-2022}
TARGET=${FP_SSH_TARGET:-grok@47.243.7.238}
REMOTE=${FP_REMOTE_DIR:-apps/first-principles}     # 相对远端 $HOME
APP_PORT=${FP_PORT:-8100}
PY=${FP_PYTHON:-/usr/bin/python3}
SSH=(ssh -i "$KEY" -p "$PORT" -o BatchMode=yes "$TARGET")

echo "==> 同步代码到 $TARGET:~/$REMOTE"
tar czf - --exclude=.venv --exclude=data --exclude=.env --exclude='*.db' --exclude=__pycache__ --exclude=.git \
    app fp_core requirements.txt run.sh \
  | "${SSH[@]}" "mkdir -p ~/$REMOTE/data && rm -rf ~/$REMOTE/app ~/$REMOTE/fp_core && tar xzf - -C ~/$REMOTE"

if [[ "${1:-}" == "--init-env" ]]; then
  echo "==> 写入服务器 .env（密钥经 stdin 传输，不会显示）"
  for v in LLM_API_KEY TYPESAFE_API_KEY FP_APP_PASSWORD; do
    [[ -n "${!v:-}" ]] || { echo "本机缺少环境变量 $v" >&2; exit 1; }
  done
  q() { local s=${1//\\/\\\\}; s=${s//\"/\\\"}; printf '"%s"' "$s"; }   # systemd EnvironmentFile 的双引号转义
  {
    printf 'LLM_API_KEY=%s\n' "$(q "$LLM_API_KEY")"
    printf 'LLM_BASE_URL=%s\n' "${LLM_BASE_URL:-https://api.x.ai/v1}"
    printf 'LLM_MODEL=%s\n' "${LLM_MODEL:-grok-4.7}"
    printf 'LLM_REASONING_EFFORT=%s\n' "${LLM_REASONING_EFFORT:-low}"
    printf 'TYPESAFE_API_KEY=%s\n' "$(q "$TYPESAFE_API_KEY")"
    printf 'FP_APP_PASSWORD=%s\n' "$(q "$FP_APP_PASSWORD")"
    printf 'FP_ALLOWED_ORIGINS=%s\n' "${FP_ALLOWED_ORIGINS:-https://kenysai.github.io}"
    printf 'FP_DB_PATH=%s\n' "/home/${TARGET%@*}/$REMOTE/data/fp.db"
  } | "${SSH[@]}" "set -e; cd ~/$REMOTE; umask 077
      old=\$(grep -E '^FP_SECRET_KEY=' .env 2>/dev/null || true)
      cat > .env.new
      if [ -n \"\$old\" ]; then echo \"\$old\" >> .env.new
      else echo \"FP_SECRET_KEY=\$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=')\" >> .env.new; fi
      mv .env.new .env; chmod 600 .env; echo \"   .env 已写入（\$(wc -l < .env) 行，权限 \$(stat -c %a .env)）\""
fi

echo "==> 安装依赖并重启服务"
"${SSH[@]}" "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
cd ~/$REMOTE
export PATH="\$HOME/.local/bin:\$PATH"
if ! command -v uv >/dev/null; then
  echo "   安装 uv（用户目录）"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
[ -x .venv/bin/python ] || uv venv --quiet --python "$PY" .venv
if ! uv pip install --quiet --python .venv/bin/python -r requirements.txt; then
  echo "   依赖在 \$(.venv/bin/python -V) 上安装失败，改用 uv 管理的 Python 3.12"
  rm -rf .venv && uv venv --quiet --python 3.12 .venv
  uv pip install --quiet --python .venv/bin/python -r requirements.txt
fi
echo "   Python: \$(.venv/bin/python -V)；\$(.venv/bin/python -c 'import fastapi,uvicorn,openai;print("fastapi",fastapi.__version__,"uvicorn",uvicorn.__version__,"openai",openai.__version__)')"
[ -f .env ] || { echo "缺少 .env，请先运行 ./deploy.sh --init-env" >&2; exit 1; }
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/first-principles.service <<UNIT
[Unit]
Description=First Principles web app (FastAPI)
After=network-online.target

[Service]
WorkingDirectory=%h/$REMOTE
EnvironmentFile=%h/$REMOTE/.env
ExecStart=%h/$REMOTE/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $APP_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --quiet first-principles.service
systemctl --user restart first-principles.service
for i in \$(seq 1 20); do
  if curl -fsS http://127.0.0.1:$APP_PORT/api/health >/dev/null 2>&1; then break; fi; sleep 0.5
done
echo "   health: \$(curl -sS http://127.0.0.1:$APP_PORT/api/health)"
systemctl --user --no-pager --lines=0 status first-principles.service | head -3
[ "\$(loginctl show-user "\$USER" -p Linger --value 2>/dev/null)" = yes ] || echo "   ⚠ 未开启 linger：退出所有 SSH 会话后服务可能停止。请让管理员执行 sudo loginctl enable-linger \$USER"
REMOTE_SCRIPT
echo "==> 完成"
