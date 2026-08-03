"""DeepSeek 分类器：判断 Tibo 的推文是否与 OpenAI Codex 额度 reset 相关"""
import json
import requests
from typing import Dict


SYSTEM_PROMPT = """你是一个 OpenAI Codex 额度监控助手。
你的任务是判断来自 OpenAI Codex 团队工程师 Tibo（X 账号 @thsottiaux）的推文，是否与"Codex 额度 reset（重置）"相关。

背景：OpenAI Codex 有使用额度限制（5 小时滚动限额、周额度等）。Tibo 作为 Codex 团队工程师，会不定期在 X 上宣布对所有用户进行额度 reset，把大家的额度恢复到 100%。这种 reset 对 Codex 用户是重大利好消息，需要第一时间获知。

请将推文分为三类：
1. 明确宣布 reset：推文中明确说已经 reset 了 Codex 额度（无论用 "reset"、"refresh"、"restore"、"top up" 等任何词），或明确说即将立即 reset
2. 暗示即将 reset：推文暗示 Codex 额度可能很快会被 reset，或透露团队正在考虑/计划 reset，或预告某个时间点会 reset
3. 无关：与 Codex 额度 reset 没有直接关系

注意：
- Tibo 多数时候会直接用 "reset" 一词，但极少数情况下会用其他表达，如 "refreshed everyone's limits"、"usage has been restored"、"we've topped everyone up"、"limits are back to 100%" 等，要靠语义判断
- 有时 Tibo 会先暗示"接下来可能会 reset"或"如果情况持续会考虑 reset"
- Codex 额度 reset 的常见触发场景：服务故障补偿、庆祝活动（如周年）、限额计算 bug 修复、5 小时滚动限额暂停/恢复等
- 不要把"Codex 的功能更新"、"模型升级"、"新版本发布"等非额度类消息误判为 reset
- 如果推文是回复别人，关注内容是否涉及额度 reset 话题
- 只在确信与 Codex 额度 reset 相关时返回 1 或 2，否则返回 3

只返回 JSON，不要任何其他文字：
{"category": 1|2|3, "confidence": 0.0-1.0, "reason": "简短中文说明"}
"""


def classify(tweet: Dict, api_key: str, model: str = "deepseek-v4-flash",
             timeout: int = 30) -> Dict:
    """
    调用 DeepSeek 对单条推文做分类。

    Args:
        tweet: 推文 dict，至少包含 title 和 summary
        api_key: DeepSeek API key
        model: 模型名，默认 deepseek-chat
        timeout: 超时秒数

    Returns:
        {"category": int, "confidence": float, "reason": str}
        若解析失败，返回 {"category": 3, "confidence": 0.0, "reason": "解析失败"}
    """
    content = f"标题：{tweet.get('title', '')}\n内容：{tweet.get('summary', '')}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        json=payload, headers=headers, timeout=timeout,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"category": 3, "confidence": 0.0, "reason": "LLM 返回解析失败"}
