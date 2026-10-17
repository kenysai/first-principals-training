"""Jev 辅助、通用 LLM 建议、Markdown 导出、示例数据。"""
from __future__ import annotations

import datetime as dt
import json
import os
import time

from fp_core.judge import JevJudge, worth_full_loop

THRESHOLD = float(os.environ.get("FP_CONFIDENCE_THRESHOLD", "0.8"))

# ---------------------------------------------------------------- Jev

def jev_mode() -> str:
    if os.environ.get("TYPESAFE_MOCK") == "1":
        return "mock"
    return "real" if os.environ.get("TYPESAFE_API_KEY") else "off"


def make_judge() -> JevJudge:
    if jev_mode() == "mock":
        from fp_core.mock import mock_jev_transport
        return JevJudge(transport=mock_jev_transport)
    return JevJudge()


def jev_state(p: dict) -> dict:
    """发给 Jev 的 state：只包含用户自己写的问题描述，不含任何模型推断。"""
    d = p.get("data", {})
    define = d.get("define", {})
    return {"problem": p["title"], "background": p.get("background", ""),
            "real_problem": define.get("problem_restated", ""), "goal": define.get("goal", ""),
            "one_sentence": d.get("feynman", {}).get("one_sentence", "")}


def _stamp() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def jev_classify(p: dict) -> tuple[dict, dict]:
    d = p["data"]
    items = [a for a in d.setdefault("decompose", {}).setdefault("assumptions", []) if (a.get("statement") or "").strip()]
    if not items:
        raise ValueError("请先在第3步写下至少一条假设")
    j = make_judge()
    t0 = time.time()
    res = j.classify(jev_state(p), [a["statement"] for a in items])
    for a, r in zip(items, res):
        a["jev"] = {"type": r["type"], "confidence": r["confidence"], "probabilities": r["probabilities"], "at": _stamp()}
        if not a.get("type"):
            a["type"] = r["type"]
            a["type_by"] = "Jev"
        a["jev_confirmed"] = a.get("type_by") == "user" and a.get("type") == r["type"]
    return p, _calls(j, t0)


def jev_has_data(p: dict) -> tuple[dict, dict]:
    d = p["data"]
    items = [a for a in d.setdefault("decompose", {}).setdefault("assumptions", []) if (a.get("statement") or "").strip()]
    if not items:
        raise ValueError("请先在第3步写下至少一条假设")
    j = make_judge()
    t0 = time.time()
    res = j.has_data(jev_state(p), [a["statement"] for a in items])
    for a, r in zip(items, res):
        a["jev_data"] = {**r, "at": _stamp()}
        if a.get("has_data") in (None, ""):
            a["has_data"] = r["answer"]
            a["has_data_by"] = "Jev"
        a["jev_data_confirmed"] = False
    return p, _calls(j, t0)


def jev_quick(p: dict) -> tuple[dict, dict]:
    q = p["data"].setdefault("quick", {})
    j = make_judge()
    t0 = time.time()
    res = j.quick_check(jev_state(p))
    for k, r in res.items():
        item = q.setdefault(k, {})
        item["jev"] = {"answer": r["answer"], "p_yes": r.get("p_yes"), "confidence": r["confidence"], "at": _stamp()}
        if item.get("answer") is None:
            item["answer"] = r["answer"]
            item["by"] = "Jev"
        item["jev_confirmed"] = False
    return p, _calls(j, t0)


def _calls(j: JevJudge, t0: float) -> dict:
    tin = sum((c.get("usage") or {}).get("input_tokens", 0) for c in j.calls)
    tout = sum((c.get("usage") or {}).get("output_tokens", 0) for c in j.calls)
    return {"backend": j.name, "model": ", ".join(sorted({str(c.get("model")) for c in j.calls})),
            "input_tokens": tin, "output_tokens": tout, "seconds": round(time.time() - t0, 3)}


def quick_verdict(q: dict) -> bool | None:
    try:
        return worth_full_loop({k: {"answer": q[k]["answer"]} for k in ("costly", "conventional_works", "same_as_others")})
    except (KeyError, TypeError):
        return None

# ---------------------------------------------------------------- 通用 LLM（可选）

_llm_cache: dict = {}


def llm_status() -> dict:
    """返回 {enabled, name, reason}。启动后第一次调用时校验一次并缓存。"""
    if "status" in _llm_cache:
        return _llm_cache["status"]
    if os.environ.get("FP_LLM_MOCK") == "1":
        st = {"enabled": True, "name": "mock-llm（示例数据）", "reason": ""}
    elif not (os.environ.get("LLM_API_KEY") and os.environ.get("LLM_MODEL")):
        st = {"enabled": False, "name": "", "reason": "未配置 LLM_API_KEY / LLM_MODEL"}
    else:
        try:
            from fp_core.llm import OpenAIChat
            c = OpenAIChat()
            if os.environ.get("FP_LLM_VALIDATE", "1") != "0":
                c.client.models.list()  # 校验 key 是否有效
            _llm_cache["client"] = c
            st = {"enabled": True, "name": c.name, "reason": ""}
        except BaseException as e:  # OpenAIChat 缺依赖时 SystemExit
            st = {"enabled": False, "name": "", "reason": f"LLM 配置无效：{str(e)[:200]}"}
    _llm_cache["status"] = st
    return st


def _llm():
    if os.environ.get("FP_LLM_MOCK") == "1":
        from fp_core.mock import MockChat
        return MockChat()
    return _llm_cache["client"]


def _lines(x) -> str:
    return "\n".join(x or [])


AI_STEPS = {"define", "feynman", "decompose", "rebuild", "premortem", "experiment", "review"}


def llm_suggest(p: dict, step: str) -> dict:
    from fp_core.llm import run_step
    if not llm_status()["enabled"]:
        raise ValueError("通用 LLM 未启用")
    if step not in AI_STEPS:
        raise ValueError("这一步不支持 AI 建议")
    ctx = (f"## 说明\n这是一个网页里的辅助建议：你的输出会作为“建议”展示给用户，由用户逐条采纳或修改。"
           f"凡是用户没明确写过的个人/公司情况，只能作为“假设”提出。\n\n## 今天日期\n{dt.date.today().isoformat()}\n\n## 用户的问题\n{p['title']}\n\n## 用户提供的背景\n{p.get('background') or '（无）'}\n\n"
           f"## 用户目前在各步骤写下的内容（都是用户自己的判断，最高优先级）\n{json.dumps(p.get('data', {}), ensure_ascii=False, indent=1)}")
    llm = _llm()
    n0 = len(getattr(llm, "calls", []) or [])
    t0 = time.time()
    o = run_step(llm, step, ctx)
    from fp_core.llm import summarize_calls
    new_calls = (getattr(llm, "calls", []) or [])[n0:]
    usage = summarize_calls(new_calls) if new_calls else {"calls": 1, "model": llm.name}
    usage["seconds"] = round(time.time() - t0, 1)
    return _map_suggestion(step, o), usage


def _map_suggestion(step: str, o: dict) -> dict:
    if step == "define":
        return {"problem_restated": o["problem_restated"], "goal": o["goal"],
                "success_criteria": _lines(o["success_criteria"]), "out_of_scope": _lines(o["out_of_scope"])}
    if step == "feynman":
        return {"one_sentence": o["one_sentence"], "analogy": o["analogy"], "unclear_points": _lines(o["unclear_points"])}
    if step == "decompose":
        return {"assumptions": [{"statement": a["statement"], "type": a["type"], "type_by": "AI", "reason": a["reason"]} for a in o["assumptions"]],
                "key_phenomenon": o["key_phenomenon"], "five_whys": o["five_whys"], "root_cause": o["root_cause_hypothesis"]}
    if step == "rebuild":
        return {"base_facts": _lines(o["base_facts"]), "recommended": o["recommended"],
                "options": [{"name": x["name"], "description": x["description"], "pros": "；".join(t.rstrip("。") for t in x["pros"]),
                             "cons": "；".join(t.rstrip("。") for t in x["cons"])} for x in o["options"]]}
    if step == "premortem":
        return {"failure_modes": o["failure_modes"], "stop_signals": _lines(o["stop_signals"])}
    if step == "experiment":
        return {"what_to_test": o["what_to_test"], "steps": _lines(o["steps"]), "duration_days": o["duration_days"],
                "metrics": [{"name": m["name"], "target": m["target"], "how": m["how_to_measure"]} for m in o["metrics"]],
                "deadline": o["deadline"], "cost": o["cost"]}
    n = o["next_iteration"]
    return {"gap_summary": o["gap_summary"], "five_whys": o["five_whys"], "overturned": o["overturned_assumptions"],
            "confirmed": _lines(o["confirmed_assumptions"]), "updated_facts": _lines(o["updated_facts"]),
            "lessons": _lines(o["lessons"]), "next_keep": _lines(n["keep"]), "next_change": _lines(n["change"]),
            "next_experiment": n["next_experiment"], "next_review_date": n["next_review_date"]}

# ---------------------------------------------------------------- Markdown 导出

QUICK_LABELS = {"costly": "做错代价大吗？", "conventional_works": "常规做法有用吗？", "same_as_others": "我的情况和别人一样吗？"}
BIASES = {"confirmation": "确认偏误（只找支持自己的证据）", "sunk_cost": "沉没成本（已经投入所以硬撑）",
          "self_blame": "自责归因（把系统问题归咎于“我不够努力”）", "availability": "可得性偏差（被最近/印象深的事带偏）",
          "overconfidence": "过度自信", "anchoring": "锚定效应（被第一个数字/方案锁住）"}


def _ul(text) -> str:
    items = [x.strip() for x in (text.split("\n") if isinstance(text, str) else (text or [])) if str(x).strip()]
    return "\n".join(f"- {x}" for x in items) if items else "- （未填写）"


def _v(x) -> str:
    return str(x).strip() if x not in (None, "") else "（未填写）"


def _cell(x) -> str:
    return str(x if x not in (None, "") else "-").replace("|", "／").replace("\n", " ")


def _yn(x) -> str:
    return {True: "是", False: "否"}.get(x, "未判断")


def export_markdown(p: dict) -> str:
    d = p.get("data", {})
    L = [f"# {p['title']}", "",
         f"- 状态：{p['status']}　领域：{p['domain']}　重要性：{p['importance']}" + ("　（示例）" if p.get("is_demo") else ""),
         f"- 创建：{p['created_at'][:10]}　更新：{p['updated_at'][:10]}　验证截止日：{p.get('deadline') or '-'}　复盘日：{p.get('review_date') or '-'}",
         "", f"**背景：** {_v(p.get('background'))}", ""]
    q = d.get("quick", {})
    L += ["## 第0步 快速判断", "", "| 问题 | 我的回答 | Jev | Jev 置信度 |", "|---|---|---|---|"]
    for k, lab in QUICK_LABELS.items():
        it = q.get(k, {})
        jv = it.get("jev") or {}
        L.append(f"| {lab} | {_yn(it.get('answer'))} | {_yn(jv.get('answer')) if jv else '-'} | {jv.get('confidence', '-') if jv else '-'} |")
    v = quick_verdict(q)
    L += ["", f"**结论：** {'值得跑完整流程' if v else ('用常规做法/类比可能就够了' if v is False else '未完成')}", ""]
    df = d.get("define", {})
    L += ["## 第1步 定义问题", "", f"**真正要解决的问题：** {_v(df.get('problem_restated'))}", "", f"**目标：** {_v(df.get('goal'))}", "",
          "**成功标准：**", _ul(df.get("success_criteria", "")), "", "**不在本次范围：**", _ul(df.get("out_of_scope", "")), ""]
    fy = d.get("feynman", {})
    L += ["## 第2步 费曼检验", "", f"**一句话：** {_v(fy.get('one_sentence'))}", "", f"**类比：** {_v(fy.get('analogy'))}", "",
          "**还讲不清的地方：**", _ul(fy.get("unclear_points", "")), ""]
    dc = d.get("decompose", {})
    L += ["## 第3步 拆到基本事实", "", "| # | 说法 | 我的标注 | Jev 标注 | Jev 置信度 | 理由 |", "|---|---|---|---|---|---|"]
    for i, a in enumerate(dc.get("assumptions", []), 1):
        jv = a.get("jev") or {}
        warn = " ⚠待确认" if jv and float(jv["confidence"]) < THRESHOLD and not a.get("jev_confirmed") else ""
        L.append(f"| {i} | {_cell(a.get('statement'))} | {_cell(a.get('type'))} | {_cell(jv.get('type'))}{warn} | "
                 f"{_cell(jv.get('confidence'))} | {_cell(a.get('reason'))} |")
    L += ["", f"**关键现象：** {_v(dc.get('key_phenomenon'))}", "", "**5个为什么：**"]
    L += [f"{i}. {_v(w.get('why'))} → {_v(w.get('answer'))}（{w.get('type') or '未标注'}）" for i, w in enumerate(dc.get("five_whys", []), 1)] or ["（未填写）"]
    L += ["", f"**根因（假设）：** {_v(dc.get('root_cause'))}", ""]
    ev = d.get("evidence", {})
    L += ["## 第4步 查证据和偏见", "", "| # | 说法 | 有数据支持？ | Jev | Jev 置信度 | 依据/要收集的数据 |", "|---|---|---|---|---|---|"]
    for i, a in enumerate(dc.get("assumptions", []), 1):
        jd = a.get("jev_data") or {}
        warn = " ⚠待确认" if jd and float(jd["confidence"]) < THRESHOLD and not a.get("jev_data_confirmed") else ""
        L.append(f"| {i} | {_cell(a.get('statement'))} | {_cell({True: '有', False: '没有'}.get(a.get('has_data')))} | "
                 f"{_cell({True: '有', False: '没有'}.get(jd.get('answer')))}{warn} | {_cell(jd.get('confidence'))} | {_cell(a.get('evidence'))} |")
    b = ev.get("biases", {})
    hit = [f"{BIASES[k]}：{b[k].get('note') or '已勾选'}" for k in BIASES if b.get(k, {}).get("checked")]
    L += ["", "**可能存在的偏见：**", _ul(hit), "", "**可变因素：**", _ul(ev.get("changeable", "")), "",
          "**不可变约束：**", _ul(ev.get("fixed", "")), ""]
    rb = d.get("rebuild", {})
    L += ["## 第5步 从事实重建", "", "**基本事实：**", _ul(rb.get("base_facts", "")), ""]
    for o in rb.get("options", []):
        star = " ⭐推荐" if o.get("name") and o.get("name") == rb.get("recommended") else ""
        L += [f"### {_v(o.get('name'))}{star}", _v(o.get("description")), "", f"- 优点：{_v(o.get('pros'))}", f"- 缺点：{_v(o.get('cons'))}", ""]
    pm = d.get("premortem", {})
    L += ["## 第6步 逆向检查", "", "| 可能怎么失败 | 可能性 | 预防 |", "|---|---|---|"]
    L += [f"| {_cell(f.get('mode'))} | {_cell(f.get('likelihood'))} | {_cell(f.get('prevention'))} |" for f in pm.get("failure_modes", [])]
    L += ["", "**停下来重新评估的信号：**", _ul(pm.get("stop_signals", "")), ""]
    ex = d.get("experiment", {})
    L += ["## 第7步 小成本验证", "", f"**试什么：** {_v(ex.get('what_to_test'))}", "", "**步骤：**", _ul(ex.get("steps", "")), "",
          f"**时长：** {_v(ex.get('duration_days'))} 天　**截止日：** {_v(ex.get('deadline'))}　**成本：** {_v(ex.get('cost'))}", "",
          "| 指标 | 目标 | 怎么测量 |", "|---|---|---|"]
    L += [f"| {_cell(m.get('name'))} | {_cell(m.get('target'))} | {_cell(m.get('how'))} |" for m in ex.get("metrics", [])]
    rv = d.get("review", {})
    L += ["", "## 第8步 复盘", "", f"**复盘日：** {_v(p.get('review_date'))}", "", "**实际结果：**"]
    for m in ex.get("metrics", []):
        act = (rv.get("metric_actuals") or {}).get(m.get("name", ""), "")
        if m.get("name"):
            L.append(f"- {m['name']}：目标 {_v(m.get('target'))}，实际 {_v(act)}")
    L += [_v(rv.get("actual")), "", f"**差距：** {_v(rv.get('gap_summary'))}", "", "**对差距的5个为什么：**"]
    L += [f"{i}. {_v(w.get('why'))} → {_v(w.get('answer'))}（{w.get('type') or '未标注'}）" for i, w in enumerate(rv.get("five_whys", []), 1)] or ["（未填写）"]
    L += ["", "**被推翻的假设：**", _ul([f"{o.get('assumption')}（证据：{o.get('evidence') or '-'}）" for o in rv.get("overturned", []) if o.get("assumption")]),
          "", "**被证实的假设：**", _ul(rv.get("confirmed", "")), "", "**更新后的事实：**", _ul(rv.get("updated_facts", "")), "",
          "**经验教训：**", _ul(rv.get("lessons", "")), "", "### 下一轮迭代", "", "**保留：**", _ul(rv.get("next_keep", "")), "",
          "**改变：**", _ul(rv.get("next_change", "")), "", f"**下一个小实验：** {_v(rv.get('next_experiment'))}", "",
          f"**下次复盘：** {_v(rv.get('next_review_date'))}", "", "---", f"导出时间：{_stamp()}（第一性原理问题拆解器）", ""]
    return "\n".join(L)

# ---------------------------------------------------------------- 示例

def demo_problem() -> dict:
    today = dt.date.today()
    dl, rd = (today + dt.timedelta(days=14)).isoformat(), (today + dt.timedelta(days=15)).isoformat()
    A = lambda s, t, r, jt, jc, hd, ev, jd, jdc: {  # noqa: E731
        "statement": s, "type": t, "type_by": "user", "reason": r,
        "jev": {"type": jt, "confidence": jc, "probabilities": {}}, "jev_confirmed": t == jt and jc >= THRESHOLD,
        "has_data": hd, "evidence": ev, "jev_data": {"answer": jd, "confidence": jdc}, "jev_data_confirmed": jdc >= THRESHOLD}
    return {
        "title": "带孩子的情况下怎么保持网球运动", "status": "解决", "domain": "健康", "importance": "中",
        "deadline": dl, "review_date": rd,
        "background": "计划周一三五打网球，只去了一天；打完球后腿抽筋、走路不便；晚上熬夜给孩子把尿，没休息好。",
        "data": {
            "quick": {"costly": {"answer": False, "jev": {"answer": False, "p_yes": 0.18, "confidence": 0.82}},
                      "conventional_works": {"answer": False, "jev": {"answer": False, "p_yes": 0.31, "confidence": 0.69}, "jev_confirmed": True},
                      "same_as_others": {"answer": False, "jev": {"answer": False, "p_yes": 0.29, "confidence": 0.71}, "jev_confirmed": True}},
            "define": {"problem_restated": "在带小孩、睡眠经常被打断的情况下，怎样稳定地保持网球运动（而不是“怎么打满一周三次”）",
                       "goal": "建立一个能持续、不伤身体的运动节奏",
                       "success_criteria": "连续 2 周每周完成 2 次\n打球后 24 小时内不抽筋\n不明显挤占睡眠", "out_of_scope": "提高比赛水平"},
            "feynman": {"one_sentence": "我想经常打网球，但带孩子让我睡不好、恢复慢，原计划太满，所以坚持不下来。",
                        "analogy": "电池老化了还按新手机的用法跑，电量撑不到晚上。", "unclear_points": "“坚持”到底指每周几次？"},
            "decompose": {
                "assumptions": [
                    A("打完球后出现了腿抽筋", "事实", "我亲身经历", "事实", 0.98, True, "我亲口陈述", True, 0.95),
                    A("夜里要给孩子把尿，睡眠被打断", "事实", "我亲身经历", "事实", 0.95, True, "我亲口陈述", True, 0.9),
                    A("睡眠不足会让肌肉恢复变慢", "事实", "公认生理常识", "事实", 0.49, None, "", False, 0.75),
                    A("抽筋主要是因为强度超过当前体能", "假设", "没记录强度", "假设", 0.98, False, "需要收集：每次时长、强度自评", False, 0.94),
                    A("一周打三次才算坚持", "惯例", "自己定的标准", "惯例", 0.77, False, "没有依据", False, 0.85),
                ],
                "key_phenomenon": "计划一周打 3 次，实际只去了 1 天",
                "five_whys": [
                    {"why": "为什么周三、周五没去？", "answer": "周一打完腿抽筋，走路不便", "type": "事实"},
                    {"why": "为什么打完会抽筋？", "answer": "可能强度超过当前体能，补水和拉伸不够", "type": "假设"},
                    {"why": "为什么恢复跟不上？", "answer": "夜里给孩子把尿，睡眠被打断", "type": "事实"},
                    {"why": "为什么计划没考虑恢复？", "answer": "沿用了“一周三次才算坚持”的标准", "type": "惯例"},
                ],
                "root_cause": "计划强度按睡眠充足的人设定，没考虑带孩子导致的恢复变慢"},
            "evidence": {"biases": {"self_blame": {"checked": True, "note": "第一反应是“我不够自律”"},
                                    "anchoring": {"checked": True, "note": "被“一周三次”锚定"}},
                         "changeable": "打球频率和时长\n拉伸和补水\n打球安排在哪天", "fixed": "夜里要给孩子把尿"},
            "rebuild": {"base_facts": "打完球后会抽筋\n夜里睡眠被打断\n睡眠不足恢复变慢", "recommended": "一周两次 + 恢复优先",
                        "options": [{"name": "一周两次 + 恢复优先", "description": "每周 2 次，中间至少隔两天；打完拉伸 10 分钟并补水",
                                     "pros": "负荷可控；容易坚持", "cons": "运动量暂时减少"},
                                    {"name": "按睡眠动态安排", "description": "只在前一晚睡得相对好的第二天打", "pros": "顺应真实约束", "cons": "计划不固定"}]},
            "premortem": {"failure_modes": [{"mode": "孩子生病，整周被打乱", "likelihood": "高", "prevention": "预留备选日，错过不追补"},
                                            {"mode": "状态好就加大强度，再次抽筋", "likelihood": "中", "prevention": "前两周每次不超过 60 分钟"}],
                          "stop_signals": "两周内抽筋 2 次以上"},
            "experiment": {"what_to_test": "每周 2 次 + 拉伸补水，能否不抽筋且坚持两周", "duration_days": 14, "deadline": dl,
                           "steps": "定好两个固定日 + 一个备选日\n每次不超过 60 分钟，打完拉伸\n记录时长、强度、饮水、是否抽筋、前一晚睡眠",
                           "cost": "每周约 3 小时",
                           "metrics": [{"name": "完成次数", "target": "4 次", "how": "日历打勾"}, {"name": "抽筋次数", "target": "0 次", "how": "打完 24 小时内记录"}]},
            "review": {},
        },
    }


def seed_if_needed(db) -> None:
    if db.meta_get("demo_seeded"):
        return
    db.create(demo_problem(), is_demo=True)
    db.meta_set("demo_seeded", "1")
