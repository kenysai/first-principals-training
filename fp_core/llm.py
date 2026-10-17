"""通用 LLM 客户端（OpenAI 兼容接口）+ JSON 解析/校验/重试。"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from .prompts import system_prompt, user_prompt
from .schemas import validate


class StepError(RuntimeError):
    def __init__(self, step: str, msg: str, raw: str = ""):
        super().__init__(f"[{step}] {msg}")
        self.step, self.raw = step, raw


def extract_json(text: str) -> Any:
    """容忍 ```json 代码块和前后多余文字。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


class OpenAIChat:
    """任意 OpenAI 兼容端点。环境变量：LLM_API_KEY / LLM_BASE_URL(可选) / LLM_MODEL。"""

    def __init__(self) -> None:
        key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL")
        if not key or not model:
            raise SystemExit("缺少环境变量：请设置 LLM_API_KEY 和 LLM_MODEL（或用 --mock 体验）。")
        try:
            from openai import OpenAI
        except ImportError:
            raise SystemExit("未安装 openai：请先 pip install -r requirements.txt")
        kwargs: dict[str, Any] = {"api_key": key}
        if os.environ.get("LLM_BASE_URL"):
            kwargs["base_url"] = os.environ["LLM_BASE_URL"]
        self.client = OpenAI(**kwargs)
        self.model = model
        self.json_mode = os.environ.get("LLM_JSON_MODE", "1") != "0"
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
        self.name = f"openai-compatible:{model}"
        self.timeout = float(os.environ.get("LLM_TIMEOUT", "180"))
        # 推理模型可选：low/medium/high。grok-4.7 设为 low 时快 5 倍以上、便宜约 5 倍（实测）
        self.reasoning_effort = os.environ.get("LLM_REASONING_EFFORT") or None
        self.calls: list[dict] = []  # 每次调用的耗时和 token 用量

    def complete(self, messages: list[dict]) -> str:
        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, temperature=self.temperature,
                                      timeout=self.timeout)
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        t0 = time.time()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # 部分服务商/模型不支持某些参数，自动去掉后重试一次
            msg = str(e)
            if self.reasoning_effort and "reasoning" in msg.lower():
                self.reasoning_effort = None
                kwargs.pop("reasoning_effort", None)
            elif self.json_mode and ("400" in msg or "response_format" in msg):
                self.json_mode = False
                kwargs.pop("response_format", None)
            else:
                raise
            resp = self.client.chat.completions.create(**kwargs)
        self.calls.append(_usage(resp, time.time() - t0))
        return resp.choices[0].message.content or ""


def _usage(resp, seconds: float) -> dict:
    u = getattr(resp, "usage", None)
    rec: dict[str, Any] = {"model": getattr(resp, "model", None), "seconds": round(seconds, 2)}
    if u is not None:
        rec["prompt_tokens"] = getattr(u, "prompt_tokens", None)
        rec["completion_tokens"] = getattr(u, "completion_tokens", None)
        det = getattr(u, "completion_tokens_details", None)
        rec["reasoning_tokens"] = getattr(det, "reasoning_tokens", None) if det else None
        ticks = getattr(u, "cost_in_usd_ticks", None)  # xAI 扩展字段：1 tick = 1e-10 美元
        if ticks is None and hasattr(u, "model_extra"):
            ticks = (u.model_extra or {}).get("cost_in_usd_ticks")
        if ticks is not None:
            rec["cost_usd"] = round(ticks / 1e10, 6)
    return rec


def summarize_calls(calls: list[dict]) -> dict:
    """汇总通用 LLM 调用：次数、总耗时、token、费用（若服务商返回）。"""
    tot = {"calls": len(calls), "seconds": round(sum(c.get("seconds") or 0 for c in calls), 1)}
    for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
        tot[k] = sum(c.get(k) or 0 for c in calls)
    costs = [c["cost_usd"] for c in calls if c.get("cost_usd") is not None]
    if costs:
        tot["cost_usd"] = round(sum(costs), 4)
    tot["model"] = ", ".join(sorted({str(c.get("model")) for c in calls if c.get("model")}))
    return tot


def run_step(client, step: str, context_block: str, verbose: bool = False) -> dict:
    """调用一次 LLM 完成一个步骤；JSON 解析或结构校验失败时把错误反馈给模型重试一次。"""
    messages = [
        {"role": "system", "content": system_prompt(step)},
        {"role": "user", "content": user_prompt(step, context_block)},
    ]
    raw = ""
    for attempt in range(2):
        raw = client.complete(messages)
        try:
            data = extract_json(raw)
            data, errors = validate(step, data)
        except (json.JSONDecodeError, ValueError) as e:
            errors = [f"不是合法 JSON：{e}"]
        if not errors:
            return data
        if verbose or attempt == 0:
            print(f"  ⚠ {step} 输出未通过校验（第{attempt + 1}次）：{'; '.join(errors[:5])}")
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "你的输出无法通过校验：\n- " + "\n- ".join(errors[:10])
             + "\n请只输出修正后的完整 JSON 对象，不要任何其他文字。"},
        ]
    raise StepError(step, "重试后仍未得到合法 JSON", raw)
