"""对正在运行的服务做端到端测试（真实 Jev + 真实通用 LLM，会消耗少量额度）。
用法：python tests/e2e_real.py [http://localhost:8000]"""
import json, os, sys, time, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
TOKEN = ""


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + TOKEN} if TOKEN else {})})
    t = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read().decode()
    return (json.loads(raw) if raw.startswith(("{", "[")) else raw), round(time.time() - t, 1)


if call("GET", "/api/health")[0].get("auth"):  # 开启了登录：用环境变量 FP_APP_PASSWORD 登录
    TOKEN = call("POST", "/api/login", {"password": os.environ["FP_APP_PASSWORD"]})[0]["token"]
cfg, _ = call("GET", "/api/config")
print("config:", cfg["jev"], cfg["llm_name"])
p, _ = call("POST", "/api/problems", {"title": "团队每周例会太多，占掉我约 12 小时，怎么减到 6 小时以内", "domain": "工作", "importance": "高",
                                       "background": "我是数据分析组的成员；每周有 5 个固定会议；其中 2 个是跨部门同步；会议邀请都是组长发的"})
pid = p["id"]
print("created", pid)
log = []


def ai(step):
    r, s = call("POST", f"/api/problems/{pid}/ai/{step}")
    u = r["usage"]
    log.append((step, s, u.get("prompt_tokens"), u.get("completion_tokens"), u.get("cost_usd")))
    print(f"AI {step}: {s}s", {k: u.get(k) for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cost_usd")})
    return r["suggestion"]


def put(data, **kw):
    r, _ = call("PUT", f"/api/problems/{pid}", {"data": data, **kw})
    return r


cur, _ = call("GET", f"/api/problems/{pid}")
d = cur["data"]
d["define"] = ai("define")
put(d)
q, s = call("POST", f"/api/problems/{pid}/jev/quick-check"); print("Jev quick:", s, "s", q["stats"])
d = q["problem"]["data"]
d["feynman"] = ai("feynman")
put(d, status="拆解")
sug = ai("decompose")
d["decompose"] = {**sug, "assumptions": [{**a, "type": "", "type_by": "AI", "ai_type": a["type"]} for a in sug["assumptions"]]}
put(d)
r, s = call("POST", f"/api/problems/{pid}/jev/classify"); print("Jev classify:", s, "s", r["stats"])
r, s = call("POST", f"/api/problems/{pid}/jev/has-data"); print("Jev has-data:", s, "s", r["stats"])
d = r["problem"]["data"]
d["evidence"] = {"biases": {"sunk_cost": {"checked": True, "note": "会议一直这么开"}}, "changeable": "我能拒绝的会议\n我参会的方式", "fixed": "组长决定会议邀请"}
put(d, status="解决")
for step in ("rebuild", "premortem", "experiment"):
    d[step] = ai(step)
    put(d)
d["review"] = {"metric_actuals": {}, "actual": "两周后每周会议时间降到 8 小时；跨部门同步改成异步文档后少了 2 小时；组长同意我只参加 1 个跨部门会"}
put(d, status="复盘", deadline=d["experiment"].get("deadline", ""))
rv = ai("review")
d["review"].update(rv)
put(d)
md, _ = call("GET", f"/api/problems/{pid}/export.md?download=0")
open(f"/tmp/fpweb-e2e-{pid}.md", "w").write(md)
final, _ = call("GET", f"/api/problems/{pid}")
for a in final["data"]["decompose"]["assumptions"]:
    jv, jd = a.get("jev", {}), a.get("jev_data", {})
    print(f"- [{a.get('ai_type')}→Jev {jv.get('type')} {jv.get('confidence')}] 数据:{jd.get('answer')} {jd.get('confidence')} | {a['statement'][:50]}")
print("TOTAL AI:", sum(x[1] for x in log), "s, cost $", round(sum(x[4] or 0 for x in log), 4))
print("pid", pid, "report /tmp/fpweb-e2e-%d.md" % pid)
