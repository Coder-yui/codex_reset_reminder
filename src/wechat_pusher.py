"""微信推送（PushPlus）"""
import requests


def push(token: str, title: str, content: str, link: str = "",
         timeout: int = 10) -> bool:
    """
    通过 PushPlus 向微信发送一条消息。

    Args:
        token: PushPlus 的 token（在 pushplus.plus 注册后获取）
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
        "token": token,
        "title": title,
        "content": text,
        "template": "txt",
    }
    try:
        resp = requests.post(
            "http://www.pushplus.plus/send",
            json=payload,
            timeout=timeout,
        )
        data = resp.json()
        # PushPlus 成功返回 {"code":200,...}
        return data.get("code") == 200
    except Exception:
        return False
