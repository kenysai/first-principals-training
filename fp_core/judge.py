"""“类型化判断”后端：Jev（TypeSafe AI）或通用 LLM 兜底。

用于三类有固定选项的判断：
  (a) 第3步：每条假设标注 事实/假设/惯例 + 置信度
  (b) 第0步：三个快速判断是/否题，决定值不值得跑完整流程
  (c) 第4步：每条说法“有没有数据支持”是/否

Jev 接口依据 TypeSafe 官方文档（https://docs.typesafe.ai/api，2026-10 查阅）：
  POST https://api.typesafe.ai/v1/systemone
  Authorization: Bearer $TYPESAFE_API_KEY
  请求 {"state": ..., "model": "jev-latest", "questions": {id: {"type": "noul"|"choice", "instructions": ..., "criteria": ...}}}
  响应 {"model": ..., "answers": {id: {"type": "noul", "noul": p} | {"type": "choice", "choice": k, "probabilities": {...}, "confidence": c}}}
2026-10-17 已用真实 key 实测，响应形状与文档一致（实测样例见 README）：
  - choice 回答带 confidence 和 probabilities；confidence 是模型给出的校准值，不等于最大概率
    （实测：probabilities 惯例 0.76，confidence 0.64），所以本工具直接用 confidence。
  - noul 回答只有 "noul"（“是”的概率），没有 confidence 字段；本工具把 max(p, 1-p) 当作置信度（本工具约定，非官方定义）。
  - 响应的 model 是实际版本号（如 jev-1.13.0），并带 usage.input_tokens/output_tokens；响应头有 x-typesafe-request-id。
  - 错误：422 {"detail":[{"loc":[...],"msg":...}]}（字段校验）；400 {"detail":{"error_type":...,"message":...}}。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .llm import run_step

JEV_URL = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai") + "/v1/systemone"

TYPE_CRITERIA = {
    "事实": "可验证的事实：用户明确陈述过的亲身情况，或公认的客观规律/常识，几乎不会被推翻",
    "假设": "看起来合理但未经验证的推断，可能被推翻；用户没明确说过的个人情况都属于这一类",
    "惯例": "只是大家习惯这么做或自己给自己定的标准，并非必然成立",
}

QUICK_QUESTIONS = {
    "costly": "这件事如果做错，代价大吗（难以反悔、影响健康/金钱/职业/重要关系）？",
    "conventional_works": "照常规做法（别人或以前的做法）去做，就能解决这个问题吗？",
    "same_as_others": "用户的情况和大多数人一样吗（没有特殊约束）？",
}


def worth_full_loop(qc: dict) -> bool:
    """代价大，或常规做法没用，或情况和别人不一样 → 值得用第一性原理。"""
    return bool(qc["costly"]["answer"] or not qc["conventional_works"]["answer"] or not qc["same_as_others"]["answer"])


def _noul(p: float) -> dict:
    return {"answer": p >= 0.5, "p_yes": round(p, 3), "confidence": round(max(p, 1 - p), 3)}


class JevError(RuntimeError):
    """把 Jev 的错误体整理成一行可读信息。"""

    def __init__(self, status: int, body: str) -> None:
        msg = body[:500]
        try:
            detail = json.loads(body).get("detail")
            if isinstance(detail, list):  # 422 字段校验
                msg = "; ".join(f"{'.'.join(map(str, d.get('loc', [])))}: {d.get('msg')}" for d in detail)
            elif isinstance(detail, dict):  # 400 等
                msg = f"{detail.get('error_type')}: {detail.get('message')}"
            elif detail:
                msg = str(detail)
        except (ValueError, AttributeError):
            pass
        hint = {401: "（API key 无效或缺失）", 403: "（无权限，可能还在 waitlist）", 429: "（限流）", 529: "（服务过载）"}.get(status, "")
        super().__init__(f"Jev 请求失败 HTTP {status}{hint}: {msg}")
        self.status = status


class JevJudge:
    """真实或模拟的 Jev 后端。transport 为 None 时走 HTTP；测试时传入 mock_jev_transport。"""

    def __init__(self, transport: Callable[[dict], dict] | None = None) -> None:
        self.transport = transport
        self.model = os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.name = "jev-mock" if transport else f"typesafe:{self.model}"
        self.calls: list[dict] = []  # 每次调用的实际模型版本、token 用量、耗时、请求 id
        if transport is None and not os.environ.get("TYPESAFE_API_KEY"):
            raise SystemExit("缺少 TYPESAFE_API_KEY")

    def _call(self, state: Any, questions: dict) -> dict:
        body = {"state": state, "model": self.model, "questions": questions}
        if self.transport:
            resp = self.transport(body)
            self.calls.append({"model": resp.get("model"), "usage": resp.get("usage"), "latency_s": 0.0,
                               "questions": len(questions)})
            return resp["answers"]
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        for attempt in range(4):
            req = urllib.request.Request(JEV_URL, data=data, method="POST", headers={
                "Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}",
                "Content-Type": "application/json",
            })
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    resp = json.loads(r.read().decode("utf-8"))
                    self.calls.append({"model": resp.get("model"), "usage": resp.get("usage"),
                                       "latency_s": round(time.time() - t0, 3), "questions": len(questions),
                                       "request_id": r.headers.get("x-typesafe-request-id")})
                    missing = [k for k in questions if k not in resp.get("answers", {})]
                    if missing:
                        raise RuntimeError(f"Jev 响应缺少回答：{missing}")
                    return resp["answers"]
            except urllib.error.HTTPError as e:
                if e.code in (429, 529) and attempt < 3:  # 官方建议指数退避
                    time.sleep(2 ** attempt)
                    continue
                raise JevError(e.code, e.read().decode("utf-8", "ignore"))
        raise RuntimeError("Jev 请求多次限流失败")

    # (b) 快速判断
    def quick_check(self, state: dict) -> dict:
        qs = {k: {"type": "noul", "instructions": v,
                  "criteria": {"true": "是", "false": "否"}} for k, v in QUICK_QUESTIONS.items()}
        ans = self._call(state, qs)
        out = {}
        for k in QUICK_QUESTIONS:
            r = _noul(float(ans[k]["noul"]))
            out[k] = {"answer": r["answer"], "confidence": r["confidence"], "p_yes": r["p_yes"],
                      "reason": f"Jev：P(是)={r['p_yes']}"}
        return out

    # (a) 假设分类
    def classify(self, state: dict, statements: list[str]) -> list[dict]:
        qs = {f"a{i}": {"type": "choice",
                        "instructions": {"statement": s,
                                         "question": "结合 `state` 中用户的问题和补充信息，`statement` 这条说法属于哪一类？"},
                        "criteria": TYPE_CRITERIA} for i, s in enumerate(statements)}
        if not qs:
            return []
        ans = self._call(state, qs)
        out = []
        for i in range(len(statements)):
            a = ans[f"a{i}"]
            out.append({"type": a["choice"], "confidence": round(float(a.get("confidence", max(a["probabilities"].values()))), 3),
                        "probabilities": a.get("probabilities", {})})
        return out

    # (c) 有没有数据支持
    def has_data(self, state: dict, statements: list[str]) -> list[dict]:
        qs = {f"d{i}": {"type": "noul",
                        "instructions": {"statement": s,
                                         "question": "`state` 里是否已有数据、记录或用户的明确陈述能支持 `statement` 这条说法？（只是推测或常识推断不算）"},
                        "criteria": {"true": "有数据或用户明确陈述支持", "false": "没有，只是推测"}}
              for i, s in enumerate(statements)}
        if not qs:
            return []
        ans = self._call(state, qs)
        return [_noul(float(ans[f"d{i}"]["noul"])) for i in range(len(statements))]


class LLMJudge:
    """兜底：没有 TYPESAFE_API_KEY 时，用通用 LLM 做这些判断。
    假设分类和“有无数据”直接沿用第3/4步 LLM 输出里的标注（不额外调用），快速判断单独调用一次 LLM。"""

    def __init__(self, llm, context_fn: Callable[[], str]) -> None:
        self.llm, self.context_fn = llm, context_fn
        self.name = f"llm-fallback({getattr(llm, 'name', 'llm')})"

    def quick_check(self, state: dict) -> dict:
        return run_step(self.llm, "quick_check", self.context_fn())

    def classify(self, state: dict, statements: list[str]) -> list[dict] | None:
        return None  # 表示沿用 LLM 自己的标注

    def has_data(self, state: dict, statements: list[str]) -> list[dict] | None:
        return None
