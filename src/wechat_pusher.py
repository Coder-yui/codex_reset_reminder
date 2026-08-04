"""微信推送（Server酱）"""
import requests


def push(sendkey: str, title: str, content: str, link: str = "",
         timeout: int = 10) -> bool:
    """
    通过 Server酱 向微信发送一条消息。

    Args:
        sendkey: Server酱的 SendKey（在 sct.ftqq.com 注册后获取）
        title: 消息标题
        content: 消息正文（支持纯文本）
        link: 推文原文链接（附在正文末尾）
        timeout: 超时秒数

    Returns:
        是否发送成功
    """
    text = content
    if link:
        text += f"\n\n原文链接：{link}"

    payload = {
        "title": title,
        "desp": text,
    }
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            json=payload,
            timeout=timeout,
        )
        data = resp.json()
        # Server酱 成功返回 {"code":0,...}
        return data.get("code") == 0
    except Exception:
        return False
