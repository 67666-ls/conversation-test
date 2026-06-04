"""
用户模拟器 — 12 种人设的多轮对话生成

接口：
  InstructionParser.parse(text) → dict
  run_simulations(instructions, max_rounds=8) → list[dict]
"""
from __future__ import annotations
import os
import re
import json
import uuid
import time
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# 12 种人设定义
# ──────────────────────────────────────────────────────────────────────────────

PERSONAS = {
    # 基础 4 种
    "cooperative": {
        "name": "配合型",
        "desc": "友好、配合，愿意提供信息，偶尔提问",
        "system": (
            "你是一个普通用户，正在接听一个客服外呼电话。"
            "你性格友好，愿意配合，会回答问题，偶尔反问。"
            "回复要自然，不超过40字，不要过于热情。"
        ),
    },
    "resistant": {
        "name": "抗拒型",
        "desc": "不耐烦，不愿透露信息，想挂断",
        "system": (
            "你是一个忙碌的普通用户，接到推销电话，非常不耐烦。"
            "你不愿提供个人信息，经常说'不需要''没兴趣''别烦我'。"
            "但不会立即挂断，会再问几句才离开。回复不超过20字。"
        ),
    },
    "curious": {
        "name": "好奇型",
        "desc": "对服务/产品感兴趣，问很多问题",
        "system": (
            "你是一个对新事物充满好奇的用户，接到客服电话很感兴趣。"
            "你会问很多细节问题：价格、使用方式、保障、对比竞品等。"
            "每次只问1-2个问题，回复不超过40字。"
        ),
    },
    "interrupted": {
        "name": "被打断型",
        "desc": "说到一半被打断，思路混乱，需要引导",
        "system": (
            "你是一个正在忙碌的用户，通话过程中经常被身边的人或事打断。"
            "你会说'等一下''啊刚才说到哪了''你再说一遍'等。"
            "思路容易跑偏，需要客服帮你找回话题。回复不超过30字。"
        ),
    },
    # 进阶 8 种
    "impatient": {
        "name": "急躁型",
        "desc": "急于结束，要快速答案",
        "system": (
            "你是个很急躁的用户，没耐心听长篇大论。"
            "总是催促客服'说重点''能不能快点''就问你这个行不行'。"
            "回复简短，语气急迫，不超过20字。"
        ),
    },
    "confused": {
        "name": "困惑型",
        "desc": "对产品/流程完全不理解，频繁问'什么意思'",
        "system": (
            "你是个不太懂技术和业务的普通用户，对很多术语和流程感到困惑。"
            "经常说'什么意思''你说的那个是啥''我不太懂'。"
            "需要客服用最简单的语言解释。回复不超过30字。"
        ),
    },
    "angry": {
        "name": "愤怒型",
        "desc": "有投诉经历，情绪激动",
        "system": (
            "你之前被这家公司坑过，现在接到电话就很生气。"
            "你会质问、投诉，说'上次你们……''怎么还打电话''要投诉你们'。"
            "但如果客服真诚道歉并解决问题，你态度会稍微软化。回复不超过40字。"
        ),
    },
    "elderly": {
        "name": "老年型",
        "desc": "反应慢，听不清，需要多次重复",
        "system": (
            "你是一位60岁以上的老年用户，耳朵有点背，反应比较慢。"
            "经常说'你说啥''声音大点''再说一遍'。"
            "对新概念接受慢，喜欢和客服聊家常。回复不超过30字，用简单词语。"
        ),
    },
    "experienced": {
        "name": "熟练型",
        "desc": "用过同类产品，直接比较，要求高",
        "system": (
            "你是个有经验的消费者，用过很多同类产品。"
            "你会直接拿竞品比较：'你们比XX怎么样''我用过XX你们有什么优势'。"
            "你要求高，不容易被忽悠，但如果真的更好会承认。回复不超过40字。"
        ),
    },
    "distracted": {
        "name": "心不在焉型",
        "desc": "在做其他事，回答敷衍",
        "system": (
            "你一边接电话一边做别的事（看视频/玩游戏/做饭）。"
            "回答很敷衍：'嗯''哦''知道了''随便'。"
            "客服说什么你基本没认真听，但偶尔会问一句'啥来着'。回复不超过15字。"
        ),
    },
    "picky": {
        "name": "挑剔型",
        "desc": "对所有方面都有意见",
        "system": (
            "你是个挑剔的用户，对任何事情都能找到问题。"
            "价格太贵、服务不好、条款有问题、竞品更好……你总能挑毛病。"
            "但如果客服全都解答了，你会考虑。回复不超过40字。"
        ),
    },
    "novice": {
        "name": "新手型",
        "desc": "第一次接触，什么都不懂，需要从头解释",
        "system": (
            "你是第一次接触这类产品/服务的新手，什么都不知道。"
            "你会问最基础的问题：'这是干嘛的''怎么用''安全吗'。"
            "客服解释后你会问更多细节。回复不超过30字。"
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# 指令解析器
# ──────────────────────────────────────────────────────────────────────────────

class InstructionParser:
    """把 Markdown 格式的外呼指令解析成结构化 dict。"""

    SECTIONS = ["Role", "Task", "Call Flow", "Constraints", "Evaluation"]

    @classmethod
    def parse(cls, text: str) -> dict:
        result: dict = {"raw": text}
        current_section = None
        lines_buf: list[str] = []

        for line in text.splitlines():
            # 匹配 # Section 或 ## Section
            m = re.match(r"^#{1,2}\s+(.+)$", line.strip())
            if m:
                if current_section and lines_buf:
                    result[current_section] = "\n".join(lines_buf).strip()
                    lines_buf = []
                current_section = m.group(1).strip()
            else:
                if current_section:
                    lines_buf.append(line)

        if current_section and lines_buf:
            result[current_section] = "\n".join(lines_buf).strip()

        # 提取关键字段
        result["role"] = result.get("Role", "")
        result["task"] = result.get("Task", "")
        result["call_flow"] = result.get("Call Flow", "")
        result["constraints"] = result.get("Constraints", "")
        return result


# ──────────────────────────────────────────────────────────────────────────────
# LLM 客户端（直接调用 OpenAI 兼容接口）
# ──────────────────────────────────────────────────────────────────────────────

def _chat(messages: list, api_key: str, base_url: str, model: str,
          temperature: float = 0.7, max_tokens: int = 256) -> str:
    """单次 chat 请求，返回 assistant 内容字符串。"""
    import http.client
    import urllib.parse

    parsed = urllib.parse.urlparse(base_url)
    host = parsed.netloc
    path_prefix = parsed.path.rstrip("/")
    endpoint = f"{path_prefix}/chat/completions"

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()

    conn = http.client.HTTPSConnection(host, timeout=30)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    conn.request("POST", endpoint, body=payload, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()

    data = json.loads(body)
    return data["choices"][0]["message"]["content"].strip()


# ──────────────────────────────────────────────────────────────────────────────
# 单轮对话驱动
# ──────────────────────────────────────────────────────────────────────────────

def _run_single_session(
    instruction_id: int,
    instruction_text: str,
    persona_key: str,
    api_key: str,
    base_url: str,
    model: str,
    max_turns: int = 8,
) -> dict:
    """运行一条 session：Agent（被测）和 Simulator（用户）交替发言。"""
    persona = PERSONAS[persona_key]
    parsed = InstructionParser.parse(instruction_text)

    # Agent 的 system prompt
    agent_system = parsed.get("raw", instruction_text)

    # 用户模拟器的 system prompt
    user_system = persona["system"]

    agent_history = [{"role": "system", "content": agent_system}]
    user_history = [{"role": "system", "content": user_system}]
    dialog: list[dict] = []

    # Agent 先发起外呼
    opening = _chat(agent_history + [{"role": "user", "content": "开始通话"}],
                    api_key, base_url, model, temperature=0.5)
    agent_history.append({"role": "user",      "content": "开始通话"})
    agent_history.append({"role": "assistant", "content": opening})
    dialog.append({"role": "agent", "content": opening, "turn": 1})

    for turn in range(2, max_turns + 1):
        # 用户回复
        user_input = _chat(
            user_history + [{"role": "user", "content": dialog[-1]["content"]}],
            api_key, base_url, model, temperature=0.8
        )
        user_history.append({"role": "user",      "content": dialog[-1]["content"]})
        user_history.append({"role": "assistant", "content": user_input})
        dialog.append({"role": "user_sim", "content": user_input, "turn": turn})

        # 停止条件：用户表示挂断
        _end_signals = ["再见", "拜拜", "挂了", "不用了", "不需要", "挂断"]
        if any(s in user_input for s in _end_signals):
            break

        # Agent 回复
        agent_reply = _chat(
            agent_history + [{"role": "user", "content": user_input}],
            api_key, base_url, model, temperature=0.5
        )
        agent_history.append({"role": "user",      "content": user_input})
        agent_history.append({"role": "assistant", "content": agent_reply})
        dialog.append({"role": "agent", "content": agent_reply, "turn": turn + 1})

    return {
        "session_id":     str(uuid.uuid4())[:8],
        "instruction_id": instruction_id,
        "persona":        persona_key,
        "persona_name":   persona["name"],
        "dialog":         dialog,
        "total_turns":    len(dialog),
        "agent_turns":    sum(1 for d in dialog if d["role"] == "agent"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 智能人设识别：根据指令文本自动匹配最相关的人设
# ──────────────────────────────────────────────────────────────────────────────

PERSONA_DETECT_PROMPT = """你是一个外呼场景分析专家。下面是12种用户人设及其描述：

{persona_descriptions}

请分析以下外呼任务指令，判断哪些人设最有可能在真实通话中出现。

# 任务指令
{instruction_text}

# 要求
1. 选出 3-6 种最相关的人设（key名）
2. 按可能性从高到低排列
3. 只返回 JSON 数组，如 ["cooperative", "resistant", "angry"]
4. 不要返回其他任何内容

你选择的应该是该场景下最可能遇到的真实用户类型。"""


def detect_personas(
    instruction_text: str,
    api_key: str,
    base_url: str = "https://gpt-agent.cc/v1",
    model: str = "deepseek-v4-flash",
    max_personas: int = 6,
) -> list[str]:
    """
    调用 LLM 分析指令文本，自动判断该场景最适合模拟哪些人设。
    返回人设 key 列表（最多 max_personas 个）。
    """
    # 构建人设描述列表
    persona_lines = []
    for key, p in PERSONAS.items():
        persona_lines.append(f"- `{key}`: {p['name']} — {p['desc']}")
    persona_desc = "\n".join(persona_lines)

    prompt = PERSONA_DETECT_PROMPT.format(
        persona_descriptions=persona_desc,
        instruction_text=instruction_text[:3000],  # 截断超长指令
    )

    try:
        response = _chat(
            [{"role": "user", "content": prompt}],
            api_key, base_url, model,
            temperature=0.3, max_tokens=256,
        )
        # 尝试解析 JSON
        response = response.strip()
        # 移除可能的 markdown 代码块标记
        if response.startswith("```"):
            response = response.split("\n", 1)[-1].rsplit("```", 1)[0]
        detected = json.loads(response)
        if not isinstance(detected, list):
            print(f"[PERSONA_DETECT] LLM 返回格式异常：{response}")
            return ["cooperative", "resistant", "curious", "angry"]  # 兜底

        # 过滤掉不存在的 key
        valid = [k for k in detected if k in PERSONAS]
        print(f"[PERSONA_DETECT] 检测到 {len(valid)} 种人设：{[PERSONAS[k]['name'] for k in valid]}")
        return valid[:max_personas] if valid else ["cooperative", "resistant", "curious"]

    except Exception as e:
        print(f"[PERSONA_DETECT] 识别失败，回退默认：{e}")
        return ["cooperative", "resistant", "curious", "angry"]


# ──────────────────────────────────────────────────────────────────────────────
# 批量运行入口
# ──────────────────────────────────────────────────────────────────────────────

def run_simulations(
    instructions: list[dict],
    max_turns: int = 8,
    personas: Optional[list[str]] = None,
    progress_callback: Optional[callable] = None,
) -> list[dict]:
    """
    对每条 instruction × 每种 persona 跑一个 session。
    api_key / base_url / model 从环境变量读取（eval_service 在运行前注入）。
    
    progress_callback(done_count) — 每生成一条 session 就调用一次，用于前端实时进度。
    """
    api_key  = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://gpt-agent.cc/v1")
    model    = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置，请在配置页填写 API Key")

    persona_keys = personas or ["cooperative", "resistant", "curious", "angry"]  # 兜底：外部没传就用基础4种
    sessions = []

    for inst in instructions:
        inst_id   = inst.get("id", 0)
        inst_text = inst.get("instruction", "")
        if not inst_text:
            continue
        for pk in persona_keys:
            try:
                session = _run_single_session(
                    inst_id, inst_text, pk,
                    api_key, base_url, model, max_turns
                )
                sessions.append(session)
            except Exception as e:
                # 单条失败不中断整批，记录错误
                sessions.append({
                    "session_id":     str(uuid.uuid4())[:8],
                    "instruction_id": inst_id,
                    "persona":        pk,
                    "persona_name":   PERSONAS[pk]["name"],
                    "dialog":         [],
                    "total_turns":    0,
                    "agent_turns":    0,
                    "error":          str(e),
                })
            # 每生成一条就回调进度
            if progress_callback:
                progress_callback(len(sessions))

    return sessions
