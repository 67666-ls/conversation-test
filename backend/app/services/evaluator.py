"""
评测引擎 — 5 维度打分 + 人工审核触发

维度：
  1. task_completion  任务完成度（0-100）
  2. communication    沟通质量（0-100）
  3. compliance       合规性（0-100）
  4. efficiency       效率（0-100）
  5. user_experience  用户体验（0-100）
"""
from __future__ import annotations
import os
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

# 各维度权重（加和=1）
DIMENSION_WEIGHTS = {
    "task_completion": 0.35,
    "communication":   0.25,
    "compliance":      0.20,
    "efficiency":      0.10,
    "user_experience": 0.10,
}

# 人工审核触发阈值
REVIEW_SCORE_THRESHOLD = 70   # 总分低于此值触发
REVIEW_DIMENSION_THRESHOLD = 60  # 任意维度低于此值触发


@dataclass
class EvalResult:
    session_id:     str
    instruction_id: int
    persona:        str
    total_turns:    int
    agent_turns:    int
    dimensions:     dict   # {dim: score}
    final_score:    float
    grade:          str    # S/A/B/C/D
    review_flag:    bool
    review_reason:  Optional[str]
    suggestions:    list[str]
    dialog:         list   # 原始对话

    def to_dict(self) -> dict:
        return asdict(self)


def _score_to_grade(score: float) -> str:
    if score >= 90: return "S"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    return "D"


class DialogEvaluator:
    """对单条 session 进行评分。"""

    def __init__(self, parsed_instruction: dict):
        self.parsed = parsed_instruction

    def evaluate(self, session: dict) -> EvalResult:
        dialog = session.get("dialog", [])
        persona = session.get("persona", "unknown")
        total_turns = session.get("total_turns", len(dialog))
        agent_turns = session.get("agent_turns", 0)

        # 有错误的 session 直接给低分
        if session.get("error"):
            dims = {k: {"score": 0.0, "reason": f"运行错误：{session['error']}"}
                    for k in DIMENSION_WEIGHTS}
            print(f"[EVALUATOR] 会话 {session.get('session_id', '?')} 有错误: {session['error']}")
            return EvalResult(
                session_id=session.get("session_id", str(uuid.uuid4())[:8]),
                instruction_id=session.get("instruction_id", 0),
                persona=persona,
                total_turns=total_turns,
                agent_turns=agent_turns,
                dimensions=dims,
                final_score=0.0,
                grade="D",
                review_flag=True,
                review_reason=f"运行错误：{session['error']}",
                suggestions=["请检查 API Key 和网络连接"],
                dialog=dialog,
            )

        dims = self._score_dimensions(dialog, session)
        # dims 格式：{dim_key: {score: float, reason: str}}
        final = sum(dims[k]["score"] * DIMENSION_WEIGHTS[k] for k in DIMENSION_WEIGHTS)
        grade = _score_to_grade(final)
        print(f"[EVALUATOR] 会话 {session.get('session_id', '?')} ({persona}): "
              f"final={final:.1f} grade={grade} turns={total_turns}")

        # 审核触发
        review_flag = False
        review_reason = None
        if final < REVIEW_SCORE_THRESHOLD:
            review_flag = True
            review_reason = f"总分 {final:.1f} 低于阈值 {REVIEW_SCORE_THRESHOLD}"
        else:
            low_dims = [k for k, v in dims.items() if v["score"] < REVIEW_DIMENSION_THRESHOLD]
            if low_dims:
                review_flag = True
                review_reason = f"维度分偏低：{', '.join(low_dims)}"

        suggestions = self._generate_suggestions(dims, dialog)

        return EvalResult(
            session_id=session.get("session_id", str(uuid.uuid4())[:8]),
            instruction_id=session.get("instruction_id", 0),
            persona=persona,
            total_turns=total_turns,
            agent_turns=agent_turns,
            dimensions=dims,
            final_score=round(final, 2),
            grade=grade,
            review_flag=review_flag,
            review_reason=review_reason,
            suggestions=suggestions,
            dialog=dialog,
        )

    def _score_dimensions(self, dialog: list, session: dict) -> dict:
        """
        基于规则对 5 个维度打分（0-100）。
        返回值：{dim: {score: float, reason: str}}
        """
        if not dialog:
            return {k: {"score": 50.0, "reason": "无对话内容，默认给50分"} for k in DIMENSION_WEIGHTS}

        agent_msgs = [d["content"] for d in dialog if d.get("role") == "agent"]
        user_msgs  = [d["content"] for d in dialog if d.get("role") == "user_sim"]
        all_text   = " ".join(agent_msgs)

        # ── ① 任务完成度：agent 是否覆盖了 task 的关键词 ──
        task_text = self.parsed.get("task", "")
        task_keywords = [w for w in task_text.split() if len(w) > 1][:10]
        reason_parts = []
        if task_keywords:
            hit_kws = [kw for kw in task_keywords if kw in all_text]
            miss_kws = [kw for kw in task_keywords if kw not in all_text]
            hit = len(hit_kws)
            task_score = min(100, 60 + hit / len(task_keywords) * 40)
            reason_parts.append(f"指令关键词 {len(task_keywords)} 个，命中 {hit} 个")
            if hit_kws:
                reason_parts.append(f"已覆盖：{', '.join(hit_kws)}")
            if miss_kws:
                reason_parts.append(f"未提及：{', '.join(miss_kws)}")
        else:
            task_score = 70.0
            reason_parts.append("指令中未提取到明确关键词，默认基础分70")
        # 如果用户挂断（负面词），扣分
        negative = ["不需要", "挂了", "投诉", "骗人", "生气"]
        neg_found = [w for w in negative if w in " ".join(user_msgs)]
        if neg_found:
            task_score = max(0, task_score - 20)
            reason_parts.append(f"用户出现负面关键词({', '.join(neg_found)})，扣20分")
        task_reason = "；".join(reason_parts)

        # ── ② 沟通质量：agent 消息平均长度、是否有问候/感谢 ──
        avg_len = sum(len(m) for m in agent_msgs) / max(len(agent_msgs), 1)
        comm_score = min(100, 50 + avg_len * 0.5)
        comm_reason_parts = [f"Agent 共 {len(agent_msgs)} 条消息，平均 {avg_len:.0f} 字"]
        polite_words = ["您好", "感谢", "请问", "方便"]
        found_polite = [w for w in polite_words if w in all_text]
        if found_polite:
            comm_score = min(100, comm_score + 10)
            comm_reason_parts.append(f"使用了礼貌用语({', '.join(found_polite)})，+10分")
        else:
            comm_reason_parts.append("未使用基本礼貌用语")
        comm_reason = "；".join(comm_reason_parts)

        # ── ③ 合规性：是否有违规词 ──
        violation_words = ["保证赚", "绝对", "100%", "诈骗", "违法", "随便说"]
        compliance_score = 100.0
        violations_found = []
        for w in violation_words:
            if w in all_text:
                compliance_score -= 30
                violations_found.append(w)
        compliance_score = max(0, compliance_score)
        if violations_found:
            compliance_reason = f"触犯合规词({', '.join(violations_found)})，每词扣30分"
        else:
            compliance_reason = "未检测到违规关键词，满分"

        # ── ④ 效率：轮次数越少越好（3-6轮为最优）──
        turns = len(dialog)
        if turns <= 6:
            efficiency_score = 90.0
            efficiency_reason = f"共 {turns} 轮对话，≤6轮为高效区间，90分"
        elif turns <= 10:
            efficiency_score = 75.0
            efficiency_reason = f"共 {turns} 轮对话，7-10轮为中等效率，75分"
        else:
            efficiency_score = max(50, 100 - (turns - 6) * 5)
            efficiency_reason = f"共 {turns} 轮对话，超过10轮效率偏低，{efficiency_score:.0f}分"

        # ── ⑤ 用户体验：用户消息中是否出现正面词 ──
        positive_words = ["好的", "可以", "了解", "谢谢", "明白", "行"]
        pos_found = [w for w in positive_words if any(w in m for m in user_msgs)]
        pos_count = len(pos_found)
        ux_score = min(100, 60 + pos_count * 8)
        if pos_found:
            ux_reason = f"用户出现 {pos_count} 个正面词({', '.join(pos_found)})，基础60+{pos_count}×8={ux_score:.0f}分"
        else:
            ux_reason = "用户未表现出正面反馈，基础60分"

        return {
            "task_completion": {"score": round(task_score, 1), "reason": task_reason},
            "communication":   {"score": round(comm_score, 1), "reason": comm_reason},
            "compliance":      {"score": round(compliance_score, 1), "reason": compliance_reason},
            "efficiency":      {"score": round(efficiency_score, 1), "reason": efficiency_reason},
            "user_experience": {"score": round(ux_score, 1), "reason": ux_reason},
        }

    def _generate_suggestions(self, dims: dict, dialog: list) -> list[str]:
        suggestions = []
        def _score(dim): return dims[dim]["score"] if isinstance(dims.get(dim), dict) else dims.get(dim, 0)
        if _score("task_completion") < 70:
            suggestions.append("任务完成度不足，建议在对话中更明确地引导用户完成目标")
        if _score("communication") < 70:
            suggestions.append("沟通质量偏低，建议增加礼貌用语和清晰的问题表述")
        if _score("compliance") < 80:
            suggestions.append("存在合规风险，请避免使用绝对性承诺语言")
        if _score("efficiency") < 70:
            suggestions.append("对话轮次过多，建议优化话术以缩短通话时长")
        if _score("user_experience") < 70:
            suggestions.append("用户体验较差，建议改善倾听和回应方式")
        return suggestions


class BatchEvaluator:
    """批量评测（预留，供外部直接调用）。"""

    def __init__(self, instructions_map: dict):
        self._evaluators = {
            inst_id: DialogEvaluator(parsed)
            for inst_id, parsed in instructions_map.items()
        }

    def evaluate_all(self, sessions: list) -> list[EvalResult]:
        results = []
        for session in sessions:
            inst_id = session.get("instruction_id", 0)
            evaluator = self._evaluators.get(inst_id, DialogEvaluator({}))
            results.append(evaluator.evaluate(session))
        return results
