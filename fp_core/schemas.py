"""极简 JSON 结构校验（不依赖 pydantic）。

规格写法：
  "str" / "int" / "bool" / "float01"(0-1 之间的数) / "date"(YYYY-MM-DD)
  ("enum", (选项...))
  ["list", 子规格, 最少条数, 最多条数]
  {字段名: 子规格, ...}            # 所有字段必填，多余字段保留
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

TYPE3 = ("enum", ("事实", "假设", "惯例"))
LEVEL = ("enum", ("高", "中", "低"))

WHY = {"why": "str", "answer": "str", "type": TYPE3}

QC = {"answer": "bool", "confidence": "float01", "reason": "str"}

SCHEMAS: dict[str, Any] = {
    # 前置快速判断（LLM 兜底时使用；Jev 后端走 judge.py）
    "quick_check": {"costly": QC, "conventional_works": QC, "same_as_others": QC},
    "define": {
        "problem_restated": "str",
        "goal": "str",
        "success_criteria": ["list", "str", 1, 6],
        "out_of_scope": ["list", "str", 0, 6],
        "questions_for_user": ["list", "str", 0, 6],
    },
    "feynman": {
        "one_sentence": "str",
        "analogy": "str",
        "unclear_points": ["list", "str", 0, 6],
    },
    "decompose": {
        "assumptions": ["list", {
            "statement": "str", "type": TYPE3, "confidence": "float01", "reason": "str",
        }, 3, 15],
        "key_phenomenon": "str",
        "five_whys": ["list", WHY, 3, 7],
        "root_cause_hypothesis": "str",
        "questions_for_user": ["list", "str", 0, 6],
    },
    "evidence": {
        "checks": ["list", {
            "statement": "str", "has_data": "bool", "data_confidence": "float01", "evidence": "str",
            "possible_biases": ["list", "str", 0, 5],
        }, 1, 15],
        "changeable_factors": ["list", "str", 0, 10],
        "fixed_constraints": ["list", "str", 0, 10],
        "overall_biases": ["list", "str", 0, 6],
        "questions_for_user": ["list", "str", 0, 6],
    },
    "rebuild": {
        "base_facts": ["list", "str", 1, 12],
        "options": ["list", {
            "name": "str", "description": "str",
            "based_on": ["list", "str", 1, 8],
            "pros": ["list", "str", 0, 6], "cons": ["list", "str", 0, 6],
        }, 1, 3],
        "recommended": "str",
        "why_recommended": "str",
    },
    "premortem": {
        "failure_modes": ["list", {
            "mode": "str", "likelihood": LEVEL, "prevention": "str",
        }, 2, 8],
        "stop_signals": ["list", "str", 0, 5],
    },
    "experiment": {
        "what_to_test": "str",
        "steps": ["list", "str", 1, 8],
        "duration_days": "int",
        "metrics": ["list", {"name": "str", "target": "str", "how_to_measure": "str"}, 1, 6],
        "deadline": "date",
        "cost": "str",
    },
    "review_plan": {
        "review_date": "date",
        "questions": ["list", "str", 3, 10],
        "data_to_collect": ["list", "str", 0, 8],
    },
    "review": {
        "gap_summary": "str",
        "five_whys": ["list", WHY, 3, 7],
        "updated_facts": ["list", "str", 0, 12],
        "overturned_assumptions": ["list", {"assumption": "str", "evidence": "str"}, 0, 10],
        "confirmed_assumptions": ["list", "str", 0, 10],
        "lessons": ["list", "str", 1, 8],
        "next_iteration": {
            "keep": ["list", "str", 0, 6],
            "change": ["list", "str", 0, 6],
            "next_experiment": "str",
            "next_review_date": "date",
        },
    },
}


def _check(value: Any, spec: Any, path: str, errors: list[str]) -> Any:
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            errors.append(f"{path or '根'} 应为对象")
            return value
        out = dict(value)
        for key, sub in spec.items():
            if key not in value:
                errors.append(f"缺少字段 {path}.{key}".replace("..", ".").lstrip("."))
                continue
            out[key] = _check(value[key], sub, f"{path}.{key}", errors)
        return out
    if isinstance(spec, list) and spec and spec[0] == "list":
        _, sub, lo, hi = spec
        if not isinstance(value, list):
            errors.append(f"{path} 应为数组")
            return value
        if len(value) > hi:  # 超出上限不算错误，截断即可（真实模型常多给几条）
            value = value[:hi]
        if len(value) < lo:
            errors.append(f"{path} 至少需要 {lo} 条，实际 {len(value)}")
        return [_check(v, sub, f"{path}[{i}]", errors) for i, v in enumerate(value)]
    if isinstance(spec, tuple) and spec[0] == "enum":
        if value not in spec[1]:
            errors.append(f"{path} 必须是 {'/'.join(spec[1])} 之一，实际 {value!r}")
        return value
    if spec == "str":
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path} 应为非空字符串")
        return value
    if spec == "bool":
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        if not isinstance(value, bool):
            errors.append(f"{path} 应为 true/false")
        return value
    if spec == "int":
        try:
            if isinstance(value, bool):
                raise ValueError
            iv = int(value)
            if float(value) != iv:
                raise ValueError
            return iv
        except (TypeError, ValueError):
            errors.append(f"{path} 应为整数")
            return value
    if spec == "float01":
        try:
            if isinstance(value, bool):
                raise ValueError
            fv = float(value)
        except (TypeError, ValueError):
            errors.append(f"{path} 应为 0-1 之间的数字")
            return value
        if not 0.0 <= fv <= 1.0:
            errors.append(f"{path} 应在 0-1 之间，实际 {fv}")
        return fv
    if spec == "date":
        try:
            _dt.date.fromisoformat(str(value))
        except ValueError:
            errors.append(f"{path} 应为 YYYY-MM-DD 日期，实际 {value!r}")
        return value
    raise ValueError(f"未知规格 {spec!r}")


def validate(step: str, data: Any) -> tuple[Any, list[str]]:
    """返回 (清洗后的数据, 错误列表)。错误列表为空即通过。"""
    errors: list[str] = []
    cleaned = _check(data, SCHEMAS[step], "", errors)
    return cleaned, errors


def list_limits(step: str) -> str:
    """把数组条数限制写成提示词里的一行说明。"""
    out: list[str] = []

    def walk(spec: Any, path: str) -> None:
        if isinstance(spec, dict):
            for k, v in spec.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(spec, list) and spec and spec[0] == "list":
            out.append(f"{path} {spec[2]}-{spec[3]} 条")
            walk(spec[1], path + "[]")

    walk(SCHEMAS[step], "")
    return "；".join(out)
