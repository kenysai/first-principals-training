"""主流程：第0步快速判断 + 8 步循环 + 交互式补充/确认 + 复盘。"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import __version__
from .judge import worth_full_loop
from .llm import StepError, run_step
from .prompts import STEP_ORDER, STEPS
from .report import render_quick_check, render_report, render_review, render_step

PAUSE_AFTER = {"define", "decompose", "evidence"}  # 只有用户知道真实情况，在这几步后停下来


class IO:
    """终端交互。auto=True 时所有提问都直接返回空（跳过）。"""

    def __init__(self, auto: bool) -> None:
        self.auto = auto

    def say(self, text: str = "") -> None:
        print(text, flush=True)

    def ask(self, prompt: str) -> str:
        """多行输入，空行结束。"""
        if self.auto:
            return ""
        print(prompt + "\n（可多行，直接回车/空行结束）", flush=True)
        lines = []
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not line.strip():
                break
            lines.append(line.strip())
        return "\n".join(lines)


class Loop:
    def __init__(self, llm, judge, io: IO, threshold: float, mock: bool) -> None:
        self.llm, self.judge, self.io, self.threshold = llm, judge, io, threshold
        self.state: dict = {"meta": {}, "user_notes": [], "quick_check": None, "steps": {}}
        self.mock = mock

    # ---------- 上下文 ----------
    def judge_state(self) -> dict:
        """发给 Jev 的 state：只含问题和用户提供的信息，不含模型推断。"""
        m = self.state["meta"]
        return {"problem": m["problem"], "background": m.get("context") or "",
                "user_provided_facts": [n["text"] for n in self.state["user_notes"]]}

    def context_block(self) -> str:
        m = self.state["meta"]
        parts = [f"## 今天日期\n{m['today']}", f"## 用户的问题\n{m['problem']}"]
        if m.get("context"):
            parts.append(f"## 用户提供的背景\n{m['context']}")
        if self.state["user_notes"]:
            parts.append("## 用户补充/更正的信息（最高优先级，是真实情况）\n"
                         + "\n".join(f"- {n['text']}" for n in self.state["user_notes"]))
        if self.state.get("quick_check"):
            parts.append("## 第0步 快速判断\n" + json.dumps(self.state["quick_check"], ensure_ascii=False))
        for step, d in self.state["steps"].items():
            parts.append(f"## {STEPS[step]['title']} 的结果\n{json.dumps(d, ensure_ascii=False, indent=1)}")
        return "\n\n".join(parts)

    def note(self, after: str, text: str) -> None:
        self.state["user_notes"].append({"after": after, "text": text})

    # ---------- 第0步 ----------
    def quick_check(self) -> bool:
        self.io.say("\n▶ 第0步 快速判断：值不值得跑完整流程…")
        qc = self.judge.quick_check(self.judge_state())
        for r in qc.values():
            r.setdefault("source", self.judge.name)
        labels = {"costly": "做错代价大吗", "conventional_works": "常规做法有用吗", "same_as_others": "你的情况和别人一样吗"}
        for k, r in qc.items():
            if float(r["confidence"]) < self.threshold and not self.io.auto:
                a = self.io.ask(f"⚠ 「{labels[k]}」模型判断为“{'是' if r['answer'] else '否'}”，置信度 {float(r['confidence']):.2f}。"
                                f"请确认：输入 y(是) / n(否)，回车表示接受")
                if a.lower()[:1] in ("y", "n", "是", "否"):
                    r.update(answer=a.lower()[:1] in ("y", "是"), confidence=1.0, source="用户确认")
        qc["worth"] = worth_full_loop(qc)
        qc["source"] = self.judge.name
        self.state["quick_check"] = qc
        self.io.say(render_quick_check(qc, self.threshold))
        return qc["worth"]

    # ---------- 类型化判断 ----------
    def apply_judge(self, step: str) -> None:
        d = self.state["steps"][step]
        if step == "decompose":
            items = d["assumptions"]
            res = self.judge.classify(self.judge_state(), [a["statement"] for a in items])
            for a, r in zip(items, res or [None] * len(items)):
                if r:
                    a["llm_type"], a["llm_confidence"] = a["type"], a["confidence"]
                    a.update(type=r["type"], confidence=r["confidence"], probabilities=r["probabilities"], source="Jev")
                else:
                    a["source"] = "LLM(未校准)"
                a["flagged"] = float(a["confidence"]) < self.threshold
        elif step == "evidence":
            items = d["checks"]
            res = self.judge.has_data(self.judge_state(), [c["statement"] for c in items])
            for c, r in zip(items, res or [None] * len(items)):
                if r:
                    c["llm_has_data"] = c["has_data"]
                    c.update(has_data=r["answer"], data_confidence=r["confidence"], p_yes=r["p_yes"], source="Jev")
                else:
                    c["source"] = "LLM(未校准)"
                c["flagged"] = float(c["data_confidence"]) < self.threshold

    def confirm_flagged(self, step: str) -> None:
        d = self.state["steps"][step]
        if step == "decompose":
            items = [(i, a) for i, a in enumerate(d["assumptions"], 1) if a.get("flagged")]
            if not items:
                return
            txt = self.io.ask("⚠ 以下分类把握不足，请确认。每行输入“编号=事实/假设/惯例”，回车跳过：\n"
                              + "\n".join(f"  {i}. {a['statement']}（模型：{a['type']}，{float(a['confidence']):.2f}）" for i, a in items))
            for m in re.finditer(r"(\d+)\s*[=＝:：]\s*(事实|假设|惯例)", txt):
                idx = int(m.group(1))
                if 1 <= idx <= len(d["assumptions"]):
                    a = d["assumptions"][idx - 1]
                    a.update(type=m.group(2), confidence=1.0, source="用户确认", flagged=False)
                    self.note("第3步", f"用户确认：「{a['statement']}」属于{m.group(2)}")
        elif step == "evidence":
            items = [(i, c) for i, c in enumerate(d["checks"], 1) if c.get("flagged")]
            if not items:
                return
            txt = self.io.ask("⚠ 以下“有没有数据支持”判断把握不足，请确认。每行输入“编号=y/n”，回车跳过：\n"
                              + "\n".join(f"  {i}. {c['statement']}（模型：{'有' if c['has_data'] else '没有'}，{float(c['data_confidence']):.2f}）" for i, c in items))
            for m in re.finditer(r"(\d+)\s*[=＝:：]\s*([yYnN有没])", txt):
                idx = int(m.group(1))
                if 1 <= idx <= len(d["checks"]):
                    c = d["checks"][idx - 1]
                    yes = m.group(2) in "yY有"
                    c.update(has_data=yes, data_confidence=1.0, source="用户确认", flagged=False)
                    self.note("第4步", f"用户确认：「{c['statement']}」{'有' if yes else '没有'}数据支持")

    # ---------- 单步 ----------
    def do_step(self, step: str) -> None:
        self.io.say(f"\n▶ {STEPS[step]['title']}…")
        self.state["steps"][step] = run_step(self.llm, step, self.context_block())
        self.apply_judge(step)
        self.io.say(render_step(step, self.state["steps"][step], self.threshold))
        if step in PAUSE_AFTER and not self.io.auto:
            while True:
                extra = self.io.ask("有需要补充或更正的事实/约束吗？（只有你知道真实情况；比如“抽筋是打完球后才出现的”）")
                if not extra:
                    break
                self.note(STEPS[step]["title"], extra)
                self.io.say(f"\n↻ 根据你的补充重新生成 {STEPS[step]['title']}…")
                del self.state["steps"][step]
                self.state["steps"][step] = run_step(self.llm, step, self.context_block())
                self.apply_judge(step)
                self.io.say(render_step(step, self.state["steps"][step], self.threshold))
            self.confirm_flagged(step)

    def run(self, problem: str, context: str, stop_if_not_worth: bool) -> dict:
        now = dt.datetime.now()
        self.state["meta"] = {"version": __version__, "problem": problem, "context": context,
                              "created_at": now.strftime("%Y-%m-%d %H:%M"), "today": now.date().isoformat(),
                              "llm": getattr(self.llm, "name", "llm"), "judge": self.judge.name,
                              "threshold": self.threshold, "mock": self.mock, "auto": self.io.auto}
        try:
            worth = self.quick_check()
            if not worth:
                if stop_if_not_worth:
                    self.state["stopped"] = "快速判断认为不必跑完整流程，已按 --stop-if-not-worth 停止。"
                    return self.state
                if not self.io.auto:
                    a = self.io.ask("快速判断认为这件事用常规做法可能就够了。仍要继续完整流程吗？输入 n 停止，回车继续")
                    if a.lower().startswith("n"):
                        self.state["stopped"] = "用户选择不继续完整流程。"
                        return self.state
            for step in STEP_ORDER:
                self.do_step(step)
        except StepError as e:
            self.state["error"] = f"{e}\n\n最后一次原始输出：\n\n```\n{e.raw[:2000]}\n```"
        except RuntimeError as e:  # 例如 JevError
            self.state["error"] = str(e)
        finally:
            calls = getattr(self.judge, "calls", None)
            if calls:
                self.state["meta"]["jev_calls"] = calls
            if getattr(self.llm, "calls", None):
                from .llm import summarize_calls
                self.state["meta"]["llm_usage"] = summarize_calls(self.llm.calls)
        return self.state


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-")
    return s[:20] or "problem"


def save(state: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{_slug(state['meta']['problem'])}"
    jp, mp = base.with_suffix(".json"), base.with_suffix(".md")
    jp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_report(state)
    if state.get("stopped"):
        md += f"\n\n> {state['stopped']}\n"
    mp.write_text(md, encoding="utf-8")
    return jp, mp


def collect_actual(state: dict, io: IO, actual: str | None) -> str:
    if actual:
        return actual
    exp = state["steps"].get("experiment", {})
    lines = []
    if exp:
        io.say(f"\n验证内容：{exp['what_to_test']}（截止 {exp['deadline']}）")
        for m in exp["metrics"]:
            v = io.ask(f"指标「{m['name']}」目标 {m['target']}，实际结果是？")
            if v:
                lines.append(f"- {m['name']}：目标 {m['target']}，实际 {v}")
    more = io.ask("还发生了什么？有什么意外、新发现的事实或约束？")
    if more:
        lines.append(f"- 其他情况：{more}")
    return "\n".join(lines)


def run_review(llm, report_path: Path, io: IO, actual: str | None, mock: bool) -> tuple[Path, Path] | None:
    state = json.loads(report_path.read_text(encoding="utf-8"))
    for key in ("review_plan",):
        if key not in state.get("steps", {}):
            io.say("⚠ 原报告没有完整跑完 8 步，复盘仍会进行，但参考信息不全。")
    if state["steps"].get("review_plan"):
        io.say(render_step("review_plan", state["steps"]["review_plan"]))
    actual_text = collect_actual(state, io, actual)
    if not actual_text.strip():
        io.say("没有输入实际结果，无法复盘。可以用 --actual \"…\" 直接传入。")
        return None
    today = dt.date.today().isoformat()
    ctx = (f"## 今天日期\n{today}\n\n## 原分析报告（JSON）\n{json.dumps(state, ensure_ascii=False, indent=1)}\n\n"
           f"## 用户提供的实际结果（最高优先级的事实）\n{actual_text}")
    io.say("\n▶ 复盘中…")
    review = run_step(llm, "review", ctx)
    rs = {"meta": {"created_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "source_report": str(report_path),
                   "problem": state["meta"]["problem"], "llm": getattr(llm, "name", "llm"), "mock": mock},
          "actual": actual_text, "review": review}
    io.say(render_step("review", review))
    base = f"{report_path.stem}.review-{dt.datetime.now():%Y%m%d-%H%M%S}"
    jp, mp = report_path.with_name(base + ".json"), report_path.with_name(base + ".md")
    jp.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.write_text(render_review(rs), encoding="utf-8")
    return jp, mp
