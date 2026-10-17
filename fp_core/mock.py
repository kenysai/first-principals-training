"""Mock 模式：不调用任何真实 API，返回固定的合法 JSON，用于离线测试和演示。

内容以“带孩子的情况下怎么保持网球运动”为例。无论输入什么问题，返回的都是这份示例数据。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re


def _d(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def canned(step: str) -> dict:
    data = {
        "quick_check": {
            "costly": {"answer": True, "confidence": 0.7, "reason": "持续失败会影响健康和信心，但可以反悔，代价中等偏高。"},
            "conventional_works": {"answer": False, "confidence": 0.75, "reason": "“一周三次”的常规计划已经试过，只完成了一天。"},
            "same_as_others": {"answer": False, "confidence": 0.85, "reason": "用户提到夜里要给孩子把尿，睡眠被打断，和常规人群不同。"},
        },
        "define": {
            "problem_restated": "在带小孩、睡眠经常被打断的情况下，怎样稳定地保持网球运动，而不是“怎么打满一周三次”。",
            "goal": "建立一个能持续执行、不伤身体的网球运动节奏。",
            "success_criteria": ["连续 2 周按计划完成每周 2 次", "打球后 24 小时内不再抽筋", "不明显挤占睡眠和学习时间"],
            "out_of_scope": ["提高比赛水平", "改变家庭分工的长期安排"],
            "questions_for_user": ["你目前一周能确定空出来的时间段有哪些？", "家里是否有人可以偶尔替你起夜？"],
        },
        "feynman": {
            "one_sentence": "我想经常打网球，但带孩子让我睡不好、恢复慢，原来的计划太满，所以坚持不下来。",
            "analogy": "就像手机电池老化了还按新手机的用法跑，电量当然撑不到晚上。",
            "unclear_points": ["“坚持”到底指每周几次才算？", "抽筋和睡眠不足各自影响有多大还不清楚"],
        },
        "decompose": {
            "assumptions": [
                {"statement": "打完球后出现了腿抽筋", "type": "事实", "confidence": 0.95, "reason": "用户明确说过"},
                {"statement": "夜里要给孩子把尿，睡眠被打断", "type": "事实", "confidence": 0.95, "reason": "用户明确说过"},
                {"statement": "睡眠不足会让肌肉恢复变慢", "type": "事实", "confidence": 0.85, "reason": "公认的生理常识"},
                {"statement": "抽筋主要是因为强度超过当前体能", "type": "假设", "confidence": 0.85, "reason": "用户没有说明运动强度，需要确认"},
                {"statement": "打球时补水和电解质不足", "type": "假设", "confidence": 0.9, "reason": "用户没提到补水情况"},
                {"statement": "一周打三次才算坚持", "type": "惯例", "confidence": 0.65, "reason": "只是给自己定的标准，也可能是用户真实的健康目标，并非必然"},
            ],
            "key_phenomenon": "计划一周打 3 次（周一、三、五），实际只去了 1 天",
            "five_whys": [
                {"why": "为什么周三、周五没去？", "answer": "周一打完后腿抽筋，走路不便", "type": "事实"},
                {"why": "为什么打完会抽筋？", "answer": "可能是强度超过当前体能，加上补水和放松不够", "type": "假设"},
                {"why": "为什么恢复跟不上？", "answer": "夜里给孩子把尿，睡眠被打断，恢复变慢", "type": "事实"},
                {"why": "为什么计划没考虑恢复？", "answer": "计划按“睡眠充足、恢复正常”的人来定", "type": "假设"},
                {"why": "为什么会这样定？", "answer": "沿用了“一周三次才算坚持”的标准", "type": "惯例"},
            ],
            "root_cause_hypothesis": "计划强度按常规人群设定，没有考虑带孩子导致的睡眠中断和恢复变慢。",
            "questions_for_user": ["周一打了多久、强度如何？", "打球时有没有补水？"],
        },
        "evidence": {
            "checks": [
                {"statement": "打完球后出现了腿抽筋", "has_data": True, "data_confidence": 0.95, "evidence": "用户亲口陈述", "possible_biases": []},
                {"statement": "抽筋主要是因为强度超过当前体能", "has_data": False, "data_confidence": 0.9, "evidence": "暂无数据，需要收集：每次打球时长、强度自评（1-10）", "possible_biases": ["可得性偏差"]},
                {"statement": "打球时补水和电解质不足", "has_data": False, "data_confidence": 0.7, "evidence": "暂无数据，需要收集：每次打球饮水量", "possible_biases": ["确认偏误"]},
                {"statement": "一周打三次才算坚持", "has_data": False, "data_confidence": 0.85, "evidence": "没有依据，属于自我设定", "possible_biases": ["锚定效应", "沉没成本"]},
            ],
            "changeable_factors": ["打球频率和时长", "热身、拉伸和补水", "打球安排在哪一天"],
            "fixed_constraints": ["夜里要给孩子把尿（用户陈述）"],
            "overall_biases": ["把一次失败归因于“自己不够自律”（基本归因错误）"],
            "questions_for_user": ["哪几天夜里通常睡得相对好？"],
        },
        "rebuild": {
            "base_facts": ["打完球后会抽筋", "夜里睡眠被打断", "睡眠不足会让恢复变慢"],
            "options": [
                {"name": "两次一周 + 恢复优先", "description": "每周 2 次，中间至少隔两天；打完拉伸 10 分钟并补水和电解质。",
                 "based_on": ["打完球后会抽筋", "睡眠不足会让恢复变慢"], "pros": ["负荷可控", "容易坚持"], "cons": ["运动量暂时减少"]},
                {"name": "按睡眠状况动态安排", "description": "只在前一晚睡得相对好的第二天打球，每周目标 2 次。",
                 "based_on": ["夜里睡眠被打断"], "pros": ["顺应真实约束"], "cons": ["计划不固定，需要每天判断"]},
            ],
            "recommended": "两次一周 + 恢复优先",
            "why_recommended": "最直接地针对“负荷超过恢复能力”这个根因，执行成本最低。",
        },
        "premortem": {
            "failure_modes": [
                {"mode": "孩子生病或连续几晚没睡好，打球日被打乱", "likelihood": "高", "prevention": "每周预留一个备选日，错过就顺延，不追补"},
                {"mode": "感觉状态好就加大强度，再次抽筋", "likelihood": "中", "prevention": "前两周每次不超过 60 分钟，强度自评不超过 7"},
                {"mode": "忘了拉伸和补水", "likelihood": "中", "prevention": "球包里固定放水壶和电解质，手机设打球后提醒"},
            ],
            "stop_signals": ["两周内再次抽筋 2 次以上", "连续一周睡眠少于 5 小时"],
        },
        "experiment": {
            "what_to_test": "每周 2 次 + 拉伸补水，能否不抽筋且坚持两周",
            "steps": ["定好每周两个固定打球日和一个备选日", "每次打球不超过 60 分钟，打完拉伸 10 分钟", "记录时长、强度自评、饮水量、是否抽筋、前一晚睡眠"],
            "duration_days": 14,
            "metrics": [
                {"name": "完成次数", "target": "4 次（两周）", "how_to_measure": "手机日历打勾"},
                {"name": "抽筋次数", "target": "0 次", "how_to_measure": "打球后 24 小时内记录"},
                {"name": "前一晚睡眠时长", "target": "仅记录，用于分析", "how_to_measure": "手表或手动记录"},
            ],
            "deadline": _d(14),
            "cost": "每周约 3 小时，电解质饮料少量费用",
        },
        "review_plan": {
            "review_date": _d(15),
            "questions": ["两周完成了几次？对照成功标准差多少？", "抽筋还出现吗？和前一晚睡眠、强度、补水有没有关系？",
                          "哪些假设被证实，哪些被推翻？", "对差距用 5 个为什么追问，根因是什么？", "下一轮保留什么、改变什么？"],
            "data_to_collect": ["每次打球时长和强度自评", "饮水量", "是否抽筋", "前一晚睡眠时长"],
        },
        "review": {
            "gap_summary": "计划 4 次，实际完成 3 次；抽筋 0 次，达到目标；错过的一次是因为孩子发烧。",
            "five_whys": [
                {"why": "为什么少了一次？", "answer": "第二周孩子发烧，那周只打了一次", "type": "事实"},
                {"why": "为什么没用备选日补上？", "answer": "备选日也被照顾孩子占用了", "type": "事实"},
                {"why": "为什么备选日也被占用？", "answer": "备选日和固定日在同一周，孩子生病时整周都受影响", "type": "假设"},
            ],
            "updated_facts": ["每周 2 次、每次 60 分钟以内并拉伸补水时，两周内没有抽筋", "孩子生病会影响整周安排"],
            "overturned_assumptions": [{"assumption": "一周三次才算坚持", "evidence": "每周两次也明显改善了状态和信心"}],
            "confirmed_assumptions": ["抽筋主要是因为强度超过当前体能"],
            "lessons": ["降低频率反而提高了完成率", "把意外当成常态来设计，计划才稳"],
            "next_iteration": {
                "keep": ["每周 2 次", "打完拉伸和补水"],
                "change": ["错过的一次不追补，直接算进“允许缺席额度”（每月 1 次）"],
                "next_experiment": "保持每周 2 次，再试两周，把单次时长提高到 75 分钟",
                "next_review_date": _d(30),
            },
        },
    }
    return data[step]


class MockChat:
    """模拟 LLM。LLM_MOCK_BAD=1 时每个步骤第一次故意返回坏 JSON，用来测试重试逻辑。"""

    name = "mock-llm"

    def __init__(self) -> None:
        self.bad_first = os.environ.get("LLM_MOCK_BAD") == "1"
        self.log: list[str] = []

    def complete(self, messages: list[dict]) -> str:
        m = re.search(r"STEP_ID: (\w+)", messages[0]["content"])
        step = m.group(1) if m else "define"
        is_retry = len(messages) > 2
        self.log.append(step + (" (retry)" if is_retry else ""))
        if self.bad_first and not is_retry:
            return "好的，这是结果：{\"oops\": "  # 故意截断
        return "```json\n" + json.dumps(canned(step), ensure_ascii=False) + "\n```"


def _h(text: str) -> float:
    return int(hashlib.md5(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def mock_jev_transport(body: dict) -> dict:
    """模拟 Jev /v1/systemone 的响应（形状按 TypeSafe 官方文档），按关键词+哈希给出确定性的概率。"""
    answers = {}
    for qid, q in body["questions"].items():
        instr = q["instructions"]
        text = json.dumps(instr, ensure_ascii=False)
        if q["type"] == "choice":
            opts = list(q["criteria"].keys())
            base = 0.6
            if re.search(r"用户明确说过|亲口|物理|定律|常识|出现了|被打断|会让", text):
                top, base = "事实", 0.8
            elif re.search(r"才算|大家|行业|通常|标准|惯例", text):
                top = "惯例"
            else:
                top = "假设"
            p_top = round(base + (0.98 - base) * _h(text), 2)
            rest = round((1 - p_top) / (len(opts) - 1), 3)
            probs = {o: (p_top if o == top else rest) for o in opts}
            answers[qid] = {"type": "choice", "choice": top, "probabilities": probs, "confidence": p_top}
        else:  # noul
            if re.search(r"代价", text):
                p = 0.82
            elif re.search(r"常规做法", text):
                p = 0.22
            elif re.search(r"和大多数人一样", text):
                p = 0.12
            elif re.search(r"出现了|被打断|用户明确|亲口", text):
                p = 0.93
            else:
                p = round(0.05 + 0.6 * _h(text), 2)
            answers[qid] = {"type": "noul", "noul": p}
    return {"model": "jev-mock", "answers": answers, "usage": {"input_tokens": 0, "output_tokens": 0}}
