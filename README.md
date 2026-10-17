# 第一性原理 · 问题拆解器（网页版）

一个把“第一性原理解决问题循环”做成网页的小工具。个人问题、工作问题都能用：每个问题一张卡片，按 **提出 → 拆解 → 解决 → 复盘 → 完成** 推进，每一步都有引导和表单。

- **不需要任何 AI 也能完整使用**：9 个步骤（第 0 步快速判断加 8 步）都有引导语和结构化表单。
- **可选 Jev 辅助**（配置 `TYPESAFE_API_KEY` 后启用）：一键给假设标注 事实/假设/惯例、判断“有没有数据支持”、回答三个快速判断题，结果都带置信度。低于阈值的标 ⚠待确认，由你采用或改掉。页面上并排显示 Jev 的标签和你的标签。
- **可选 AI 建议**（配置通用 LLM 后启用）：在定义问题、费曼检验、假设清单和 5 个为什么、重建方案、逆向检查、验证计划、复盘这几步，点“✨ AI 建议”会弹出建议清单，你逐条勾选后才会写入。AI 被要求**不编造你的个人情况**，它的猜测一律作为“假设”提出。
- 支持导出 Markdown 报告（中文）和 JSON；数据存在 SQLite 里；内置一个可以删除的“网球”示例。
- 所有 API key 只在服务器端读取，前端拿不到。

## 9 个步骤和对应的方法

| 步骤 | 内容 | 方法来源 |
|---|---|---|
| 0 快速判断 | 做错代价大吗？常规做法有用吗？我的情况和别人一样吗？ | 第一性原理的适用边界 |
| 1 定义问题 | 真正要解决的问题、目标、可衡量的成功标准 | 防止把方案当问题 |
| 2 费曼检验 | 一句话讲清问题、打个比方、列出讲不清的地方 | 费曼 |
| 3 拆到基本事实 | 假设清单（逐条标注 事实/假设/惯例）、关键现象、5 个为什么、根因 | 马斯克 |
| 4 查证据和偏见 | 每条假设有没有数据支持；偏见自查（确认偏误、沉没成本、自责归因等）；可变因素和不可变约束 | 芒格 |
| 5 从事实重建 | 可以一键带入第 3、4 步里的事实和约束；给出 1-3 个方案并选一个推荐 | 马斯克 |
| 6 逆向检查 | 方案可能怎么失败、可能性多大、怎么预防；出现哪些信号要停下来 | 芒格：反过来想 |
| 7 小成本验证 | 试什么、步骤、持续天数、截止日、复盘日、指标 | 快速试错 |
| 8 复盘 | 逐项填写指标的实际结果；对差距追问 5 个为什么；记录被推翻的假设、更新后的事实、下一轮计划；可以一键“基于下一轮新建问题” | 迭代 |

在某一步填好内容后，问题的状态会自动往前推进，你也可以随时手动修改状态。

## 本地运行

需要 Python 3.10 或更高版本。

```bash
cd first-principles-web
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 可选：配置 key（见下）
uvicorn app.main:app --port 8000                       # 或 ./run.sh
```

然后打开 http://localhost:8000 。

## 环境变量

| 变量 | 作用 |
|---|---|
| `TYPESAFE_API_KEY` | 启用 Jev 辅助（类型化判断）。不设置时 Jev 按钮显示为不可用 |
| `TYPESAFE_MODEL` | 默认 `jev-latest` |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 启用 AI 建议。支持任意 OpenAI 兼容服务；启动后第一次访问时会校验 key，无效就自动隐藏 AI 按钮（设置里会显示原因） |
| `LLM_REASONING_EFFORT` | 推理模型的推理强度。用 grok-4.7 时建议设为 `low`：实测每次建议约 8-38 秒，强度高时会慢很多 |
| `FP_CONFIDENCE_THRESHOLD` | 置信度阈值，默认 0.8（页面右上角的设置里也可以按浏览器单独调整） |
| `FP_DB_PATH` | SQLite 文件位置，默认 `./data/fp.db` |
| `TYPESAFE_MOCK=1` / `FP_LLM_MOCK=1` | 离线演示和测试用的模拟模式 |

**Grok（xAI）示例：**
```bash
export LLM_API_KEY="xai-..." LLM_BASE_URL="https://api.x.ai/v1" LLM_MODEL="grok-4.7" LLM_REASONING_EFFORT="low"
export TYPESAFE_API_KEY="..."
```

**OpenAI 示例：**
```bash
export LLM_API_KEY="sk-..." LLM_MODEL="gpt-4o-mini"      # 不用设置 LLM_BASE_URL
```

关于 Jev：TypeSafe 的 Jev 只返回类型化的判断和概率，不生成文字。是/否题只返回“是”的概率 p，本工具用 max(p, 1-p) 作为置信度，这是工具自己的约定；选择题直接使用 Jev 返回的 `confidence`。发给 Jev 的内容只有你写的问题、背景和定义，不包含 AI 的推断。官网上的速度、价格和“零幻觉”说法都是厂商自己的宣传。

## 登录与安全

- 设置 `FP_APP_PASSWORD` 后启用密码登录。登录成功会返回一个签名令牌（HMAC-SHA256，用 `FP_SECRET_KEY` 签名，默认有效 30 天，可用 `FP_TOKEN_DAYS` 修改），前端把它存在 localStorage 里。除了 `/api/login` 和 `/api/health`，所有 `/api/*` 接口都需要带上 `Authorization: Bearer <token>`。右上角“退出”会清除令牌，令牌过期或失效时会自动回到登录页。
- 更换 `FP_SECRET_KEY` 会让所有已登录设备失效。没设置它时每次启动随机生成一个，重启后需要重新登录。
- 登录限流：每个 IP 每分钟最多尝试 5 次（存在内存里，重启后清零）。客户端 IP 优先取 `CF-Connecting-IP`，其次取 `X-Forwarded-For` 的第一个地址。
- 没设置 `FP_APP_PASSWORD` 时**不启用登录**，只适合在本机开发时使用。
- CORS：允许 `FP_ALLOWED_ORIGINS` 里的来源（逗号分隔，默认 `https://kenysai.github.io`），以及本地开发用的 `http://localhost:*` 和 `http://127.0.0.1:*`。

## 拆分部署：前端放 GitHub Pages，后端放自己的服务器

```
浏览器 ──> https://kenysai.github.io/<repo>/   （静态前端，static/config.js 里写着 API 地址）
      └──> https://firstp.cheeshare.club/api/*  （FastAPI 后端，密码登录，key 只存在服务器上）
```

**前端（GitHub Pages）**
1. 把本目录作为仓库根目录推送到 GitHub（`.gitignore` 已经排除 `.env`、数据库、`.venv/`）。
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**。
3. `.github/workflows/pages.yml` 会在 `app/static/` 有改动时自动构建并发布。构建时会把 `static/config.js` 改写为 `window.FP_API_BASE = "https://firstp.cheeshare.club"`（可以用仓库变量 `FP_API_BASE` 覆盖）。
4. 前端用的都是相对路径，放在 `/<repo>/` 子路径下也能正常工作。后端自己也能提供同一套前端（访问 API 域名的根路径即可）。

**后端（自己的服务器，不需要 sudo 和 docker）**
- `./deploy.sh --init-env`：首次部署。它会打包同步代码，把本机环境变量里的 `LLM_API_KEY`、`TYPESAFE_API_KEY`、`FP_APP_PASSWORD` 经 stdin 写入服务器上的 `~/apps/first-principles/.env`（权限 600，不会在输出里显示），并在服务器上随机生成 `FP_SECRET_KEY`；然后用户目录里的 `uv` 创建虚拟环境、安装依赖，安装并启动 `systemctl --user` 服务 `first-principles.service`（监听 `127.0.0.1:8100`，`Restart=always`，开机自启）。
- `./deploy.sh`：之后更新代码时用，会保留服务器上已有的 `.env` 和数据库。
- 默认部署到 `grok@47.243.7.238`（SSH 端口 2022），可以用 `FP_SSH_TARGET`、`FP_SSH_PORT`、`FP_SSH_KEY` 改成其他主机。默认使用服务器自带的 Python（已在 3.14 上验证）；依赖装不上时会自动改用 uv 管理的 3.12，也可以用 `FP_PYTHON` 指定。
- 服务器需要开启 linger（`sudo loginctl enable-linger grok`），否则退出所有 SSH 会话后，`systemctl --user` 服务可能会停止。
- 数据库位置：`~/apps/first-principles/data/fp.db`，首次启动会自动放入示例问题。
- 查看日志：`journalctl --user -u first-principles -f`；重启：`systemctl --user restart first-principles`。

**公网入口（推荐：Cloudflare Tunnel）**
服务器上的 443 端口被 sing-box 占用，所以 Caddy 启动失败（`listen tcp :443: bind: address already in use`）。Cloudflare 访问源站 443 时连到的是 sing-box，于是返回 403（错误代码 1034，Edge IP Restricted）。不需要 root 的解决办法是用 Cloudflare Tunnel：
1. Cloudflare 后台 → Zero Trust → Networks → Tunnels → Create a tunnel（选 cloudflared），起名例如 `firstp`，复制 token。
2. 在隧道的 Public Hostname 里添加：`firstp.cheeshare.club`，类型 HTTP，URL 填 `127.0.0.1:8100`。如果提示已有 DNS 记录，先在 DNS 里删掉 `firstp` 原来的 A/AAAA 记录。
3. 在本机设置 `CF_TUNNEL_TOKEN` 后运行 `./tunnel.sh`。它会在服务器上把 cloudflared 装成 `systemctl --user` 服务 `cloudflared-firstp.service`，token 经 stdin 写入 `~/.config/cloudflared/token`（权限 600）。

**Docker（可选，其他平台）**
```bash
docker build -t fp-web .
docker run -p 8000:8000 -v fp-data:/data --env-file .env fp-web
```
Render 和 Railway 也可以用这个 Dockerfile。环境变量在平台后台填写；SQLite 需要挂载持久化磁盘，并把 `FP_DB_PATH` 指到挂载路径上。

## 测试

```bash
python -m unittest discover -s tests -p 'test_*.py'   # 离线：API、登录、限流、CORS（模拟 Jev 和 LLM，临时数据库）
python tests/e2e_real.py http://localhost:8000   # 对正在运行、且未开启登录的服务做真实端到端测试（会消耗少量额度）
```

## 文件结构

```
app/main.py      FastAPI 路由、鉴权中间件、CORS
app/auth.py      密码登录、令牌、限流
app/db.py        SQLite 存储
app/logic.py     Jev 辅助、AI 建议、Markdown 导出、示例数据
app/static/      单页前端（原生 HTML/CSS/JS，不需要构建）
fp_core/         与命令行版共用的核心（提示词、校验、Jev 适配器、LLM 客户端）
tests/           测试
Dockerfile, run.sh, deploy.sh, tunnel.sh, .env.example
.github/workflows/pages.yml   前端发布到 GitHub Pages
```

## 局限

- 只有一个共享密码，没有多用户账号。多人同时编辑同一个问题时，后保存的会覆盖先保存的。
- AI 建议每次要 8-38 秒（grok-4.7 加 low 推理强度），而且每次都会把整个问题的内容作为上下文发出去。
- 导出报告里的“⚠待确认”按服务器的阈值计算，不跟随浏览器里单独设置的阈值。
- AI 建议的假设偶尔会把从你的话里推出来的结论标成“事实”，所以最好再用 Jev 标注一遍，低置信度的条目会被标出来，但最终都要由你确认。
