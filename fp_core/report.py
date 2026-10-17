"""把结果渲染成中文 Markdown。"""
from __future__ import annotations

from .prompts import STEPS


def _ul(items) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- （无）"


def _conf(c) -> str:
    return "-" if c is None else f"{float(c):.2f}"


def render_quick_check(qc: dict, threshold: float) -> str:
    names = {"costly": "做错代价大吗？", "conventional_works": "常规做法有用吗？", "same_as_others": "情况和别人一样吗？"}
    rows = ["| 问题 | 回答 | 置信度 | 说明 |", "|---|---|---|---|"]
    for k, label in names.items():
        r = qc[k]
        flag = " ⚠待确认" if r.get("source") != "用户确认" and float(r["confidence"]) < threshold else ""
        rows.append(f"| {label} | {'是' if r['answer'] else '否'}{flag} | {_conf(r['confidence'])} | {r.get('reason', '')} |")
    verdict = "✅ 值得跑完整流程" if qc["worth"] else "⚪ 可能用常规做法/类比就够了"
    return f"## 第0步 快速判断（判断来源：{qc.get('source', '')}）\n\n" + "\n".join(rows) + f"\n\n**结论：{verdict}**\n"


def render_step(step: str, d: dict, threshold: float = 0.8) -> str:
    t = STEPS[step]["title"]
    if step == "define":
        return (f"## {t}\n\n**真正的问题：** {d['problem_restated']}\n\n**目标：** {d['goal']}\n\n"
                f"**成功标准：**\n{_ul(d['success_criteria'])}\n\n**不在本次范围：**\n{_ul(d['out_of_scope'])}\n\n"
                f"**需要你确认：**\n{_ul(d['questions_for_user'])}\n")
    if step == "feynman":
        return (f"## {t}\n\n**一句话：** {d['one_sentence']}\n\n**类比：** {d['analogy']}\n\n"
                f"**还讲不清的地方：**\n{_ul(d['unclear_points'])}\n")
    if step == "decompose":
        rows = ["| # | 说法 | 类型 | 置信度 | 来源 | 理由 |", "|---|---|---|---|---|---|"]
        for i, a in enumerate(d["assumptions"], 1):
            flag = " ⚠待确认" if a.get("flagged") else ""
            rows.append(f"| {i} | {a['statement']} | {a['type']}{flag} | {_conf(a['confidence'])} | {a.get('source', 'LLM')} | {a['reason']} |")
        whys = "\n".join(f"{i}. {w['why']} → {w['answer']}（{w['type']}）" for i, w in enumerate(d["five_whys"], 1))
        return (f"## {t}\n\n**假设清单**（置信度 = 对分类标注的把握，低于 {threshold} 标 ⚠ 需要你确认）\n\n" + "\n".join(rows)
                + f"\n\n**关键现象：** {d['key_phenomenon']}\n\n**5个为什么：**\n{whys}\n\n"
                f"**根因（假设）：** {d['root_cause_hypothesis']}\n\n**需要你确认：**\n{_ul(d['questions_for_user'])}\n")
    if step == "evidence":
        rows = ["| # | 说法 | 有数据支持？ | 置信度 | 来源 | 依据 | 可能的偏见 |", "|---|---|---|---|---|---|---|"]
        for i, c in enumerate(d["checks"], 1):
            flag = " ⚠待确认" if c.get("flagged") else ""
            rows.append(f"| {i} | {c['statement']} | {'有' if c['has_data'] else '没有'}{flag} | {_conf(c.get('data_confidence'))} | "
                        f"{c.get('source', 'LLM')} | {c['evidence']} | {'、'.join(c['possible_biases']) or '-'} |")
        return (f"## {t}\n\n" + "\n".join(rows) + f"\n\n**可变因素：**\n{_ul(d['changeable_factors'])}\n\n"
                f"**不可变约束：**\n{_ul(d['fixed_constraints'])}\n\n**整体要警惕的偏见：**\n{_ul(d['overall_biases'])}\n\n"
                f"**需要你确认：**\n{_ul(d['questions_for_user'])}\n")
    if step == "rebuild":
        opts = []
        for o in d["options"]:
            star = " ⭐推荐" if o["name"] == d["recommended"] else ""
            opts.append(f"### {o['name']}{star}\n{o['description']}\n\n- 依据：{'；'.join(o['based_on'])}\n"
                        f"- 优点：{'；'.join(o['pros']) or '-'}\n- 缺点：{'；'.join(o['cons']) or '-'}\n")
        return (f"## {t}\n\n**基本事实：**\n{_ul(d['base_facts'])}\n\n" + "\n".join(opts)
                + f"\n**推荐：** {d['recommended']}。{d['why_recommended']}\n")
    if step == "premortem":
        rows = ["| 可能怎么失败 | 可能性 | 预防 |", "|---|---|---|"]
        rows += [f"| {f['mode']} | {f['likelihood']} | {f['prevention']} |" for f in d["failure_modes"]]
        return f"## {t}\n\n" + "\n".join(rows) + f"\n\n**停下来重新评估的信号：**\n{_ul(d['stop_signals'])}\n"
    if step == "experiment":
        rows = ["| 指标 | 目标 | 怎么测量 |", "|---|---|---|"]
        rows += [f"| {m['name']} | {m['target']} | {m['how_to_measure']} |" for m in d["metrics"]]
        return (f"## {t}\n\n**验证什么：** {d['what_to_test']}\n\n**步骤：**\n{_ul(d['steps'])}\n\n"
                f"**时长：** {d['duration_days']} 天　**截止日：** {d['deadline']}　**成本：** {d['cost']}\n\n" + "\n".join(rows) + "\n")
    if step == "review_plan":
        return (f"## {t}\n\n**复盘日期：** {d['review_date']}\n\n**复盘时要问：**\n{_ul(d['questions'])}\n\n"
                f"**实验期间要记录：**\n{_ul(d['data_to_collect'])}\n")
    if step == "review":
        whys = "\n".join(f"{i}. {w['why']} → {w['answer']}（{w['type']}）" for i, w in enumerate(d["five_whys"], 1))
        over = _ul([f"{o['assumption']}（证据：{o['evidence']}）" for o in d["overturned_assumptions"]])
        n = d["next_iteration"]
        return (f"## 复盘\n\n**差距：** {d['gap_summary']}\n\n**对差距的5个为什么：**\n{whys}\n\n"
                f"**更新后的事实：**\n{_ul(d['updated_facts'])}\n\n**被推翻的假设：**\n{over}\n\n"
                f"**被证实的假设：**\n{_ul(d['confirmed_assumptions'])}\n\n**经验教训：**\n{_ul(d['lessons'])}\n\n"
                f"## 下一轮迭代\n\n**保留：**\n{_ul(n['keep'])}\n\n**改变：**\n{_ul(n['change'])}\n\n"
                f"**下一个小实验：** {n['next_experiment']}\n\n**下次复盘：** {n['next_review_date']}\n")
    raise KeyError(step)


def _header(meta: dict) -> str:
    mock = ""
    if meta.get("mock"):
        real_jev = meta.get("judge", "").startswith("typesafe:")
        mock = ("\n> ⚠ Mock 模式：通用 LLM 的内容是内置示例数据" + ("；Jev 的类型化判断（来源标为 Jev 的类型/置信度、第0步）是真实调用结果。\n"
                if real_jev else "，不是真实模型输出。\n"))
    ctx = f"\n**背景：** {meta['context']}\n" if meta.get("context") else ""
    calls = meta.get("jev_calls") or []
    if calls:
        tin = sum((c.get("usage") or {}).get("input_tokens", 0) for c in calls)
        tout = sum((c.get("usage") or {}).get("output_tokens", 0) for c in calls)
        lat = sum(c.get("latency_s") or 0 for c in calls)
        ver = ", ".join(sorted({str(c.get("model")) for c in calls}))
        mock += (f"- Jev 调用：{len(calls)} 次，实际版本 {ver}，输入 {tin} / 输出 {tout} tokens，"
                 f"总耗时 {lat:.2f}s\n")
    u = meta.get("llm_usage")
    if u:
        cost = f"，费用约 ${u['cost_usd']}" if "cost_usd" in u else ""
        mock += (f"- 通用 LLM 调用：{u['calls']} 次，模型 {u['model']}，输入 {u['prompt_tokens']} / 输出 {u['completion_tokens']} tokens"
                 f"（其中推理 {u['reasoning_tokens']}），总耗时 {u['seconds']}s{cost}\n")
    return (f"- 生成时间：{meta['created_at']}\n- 通用 LLM：{meta['llm']}\n- 类型化判断：{meta['judge']}"
            f"（置信度阈值 {meta['threshold']}）\n{mock}\n**原始问题：** {meta['problem']}\n{ctx}")


def render_report(state: dict) -> str:
    meta, th = state["meta"], state["meta"]["threshold"]
    parts = [f"# 第一性原理分析报告\n\n{_header(meta)}"]
    if state.get("user_notes"):
        parts.append("## 你补充/更正的信息\n\n" + _ul(f"（{n['after']}后）{n['text']}" for n in state["user_notes"]))
    if state.get("quick_check"):
        parts.append(render_quick_check(state["quick_check"], th))
    for step, d in state["steps"].items():
        parts.append(render_step(step, d, th))
    if state.get("error"):
        parts.append(f"## ❌ 中断\n\n{state['error']}\n")
    parts.append("---\n复盘：到截止日后运行 `python fp.py review <本报告的 .json 文件>`\n")
    return "\n\n".join(parts)


def render_review(review_state: dict) -> str:
    m = review_state["meta"]
    mock = "\n> ⚠ Mock 模式：以下是内置示例数据，不是真实模型输出。\n" if m.get("mock") else ""
    return (f"# 复盘报告\n\n- 生成时间：{m['created_at']}\n- 原报告：{m['source_report']}\n- 原问题：{m['problem']}\n{mock}\n"
            f"## 你提供的实际结果\n\n{review_state['actual']}\n\n" + render_step("review", review_state["review"]))
