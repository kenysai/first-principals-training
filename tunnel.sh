#!/usr/bin/env bash
# 用 Cloudflare Tunnel 把服务器上的 127.0.0.1:8100 发布到 firstp.cheeshare.club（无需 root、不占 443 端口）。
#
# 前提：在 Cloudflare Zero Trust → Networks → Tunnels 创建一个 cloudflared 隧道，
#       Public hostname 设为 firstp.cheeshare.club → HTTP → 127.0.0.1:8100，并复制隧道 token。
# 用法：把 token 放进本机环境变量 CF_TUNNEL_TOKEN，然后运行 ./tunnel.sh（token 经 stdin 传输，不会显示）。
set -euo pipefail
cd "$(dirname "$0")"
KEY=${FP_SSH_KEY:-$HOME/.ssh/kenny_server_ed25519}
PORT=${FP_SSH_PORT:-2022}
TARGET=${FP_SSH_TARGET:-grok@47.243.7.238}
SSH=(ssh -i "$KEY" -p "$PORT" -o BatchMode=yes "$TARGET")
[[ -n "${CF_TUNNEL_TOKEN:-}" ]] || { echo "请先设置 CF_TUNNEL_TOKEN" >&2; exit 1; }

printf '%s' "$CF_TUNNEL_TOKEN" | "${SSH[@]}" 'umask 077; mkdir -p ~/.config/cloudflared && cat > ~/.config/cloudflared/token && chmod 600 ~/.config/cloudflared/token'
"${SSH[@]}" "bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p ~/.local/bin ~/.config/systemd/user
if [ ! -x ~/.local/bin/cloudflared ]; then
  curl -fsSL -o ~/.local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x ~/.local/bin/cloudflared
fi
cat > ~/.config/systemd/user/cloudflared-firstp.service <<'UNIT'
[Unit]
Description=Cloudflare Tunnel for firstp.cheeshare.club
After=network-online.target first-principles.service

[Service]
ExecStart=%h/.local/bin/cloudflared tunnel --no-autoupdate run --token-file %h/.config/cloudflared/token
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cloudflared-firstp.service
sleep 5
systemctl --user --no-pager --lines=5 status cloudflared-firstp.service | head -8
REMOTE
echo "完成。几十秒后测试：curl https://firstp.cheeshare.club/api/health"
