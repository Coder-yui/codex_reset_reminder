"""飞书自定义机器人推送"""
import requests


def push(webhook_url: str, title: str, content: str, link: str = "",
         timeout: int = 10) -> bool:
    """
    向飞书群发送一条文本消息。

    Args:
        webhook_url: 飞书自定义机器人 webhook
        title: 消息标题（如 "Tibo 明确宣布 Reset（0.92）"）
        content: 消息正文
        link: 推文原文链接
        timeout: 超时秒数

    Returns:
        是否发送成功
    """
    text = f"【{title}】\n\n{content}"
    if link:
        text += f"\n\n原文链接：{link}"

    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        data = resp.json()
        # 飞书成功返回 {"StatusCode":0} 或 {"code":0,...}，失败返回非 0
        return data.get("StatusCode", -1) == 0 or data.get("code", -1) == 0
    except Exception:
        return False
