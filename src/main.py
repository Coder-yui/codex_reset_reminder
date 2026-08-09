"""主流程：拉取 → 去重 → 分类 + 关键词兜底 → 推送 → 持久化"""
import os
import re
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

# 让 main.py 既能被 `python src/main.py` 跑，也能被 `python -m src.main` 跑
sys.path.insert(0, str(Path(__file__).parent))

from multi_source_client import fetch_tweets
from rsshub_client import fetch_tweet_detail
from deduper import load_sent, save_sent, filter_new
from classifier import classify
from feishu_pusher import push as feishu_push
from wechat_pusher import push as wechat_push


SENT_FILE = Path(__file__).parent / "sent_tweets.json"


def contains_reset(tweet: dict) -> bool:
    """硬性关键词检测：推文标题或正文中是否出现 reset 字样（不区分大小写）。

    作为 LLM 分类的兜底，确保任何含 reset 的推文都不会被遗漏。
    """
    text = f"{tweet.get('title', '')} {tweet.get('summary', '')}".lower()
    return "reset" in text


def strip_html(html: str) -> str:
    """清理 RSS summary 里的 HTML 标签，转为纯文本。

    RSSHub 的 twitter 路由返回的 description 含 <br>、<hr>、<img> 等标签，
    需要清理后才能在飞书文本消息里正常展示。
    """
    if not html:
        return ""
    # <br> / <br/> 转换行
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # <hr> 转分隔线
    text = re.sub(r"<hr[^>]*/?>", "\n---\n", text, flags=re.IGNORECASE)
    # 去掉其他所有 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # HTML 实体解码（常见的一些）
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    # 压缩多余空行（保留有意义的换行）
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_time(pub_date: str) -> str:
    """将 RSS 的 pubDate（RFC822 格式）转为易读的本地时间字符串。

    输入示例：Tue, 04 Aug 2026 03:37:12 GMT
    输出示例：2026-08-04 11:37 (北京时间)
    若解析失败则原样返回。
    """
    if not pub_date:
        return "未知时间"
    try:
        dt = parsedate_to_datetime(pub_date)
        # 转为东八区时间
        from datetime import timezone, timedelta
        cst = dt.astimezone(timezone(timedelta(hours=8)))
        return cst.strftime("%Y-%m-%d %H:%M") + " (北京时间)"
    except Exception:
        return pub_date


def main():
    load_dotenv()

    rsshub_url = os.getenv("RSSHUB_URL")
    username = os.getenv("TWITTER_USERNAME", "thsottiaux")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL")
    serverchan_key = os.getenv("SERVERCHAN_KEY")
    threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
    # GitHub Actions 中未创建 Secret 时会注入空字符串，因此也要回退默认值。
    xcancel_url = os.getenv("XCANCEL_URL") or "https://xcancel.com"
    recovery_tweet_ids = [
        value.strip()
        for value in os.getenv("RECOVERY_TWEET_IDS", "").split(",")
        if value.strip()
    ]

    if not deepseek_key:
        print("[WARN] DEEPSEEK_API_KEY 未配置，将只使用 reset 关键词判断")

    # 1. 并行读取两个独立来源，取帖子并集
    print(f"[1/4] 拉取 @{username} 的最近推文...")
    try:
        tweets = fetch_tweets(rsshub_url, xcancel_url, username)
    except Exception as e:
        print(f"[ERROR] 拉取失败: {e}")
        return
    # 已知被用户时间线漏掉的帖子走单条详情路由补取。去重文件会保证只推一次。
    for tweet_id in recovery_tweet_ids:
        try:
            recovery_tweet = fetch_tweet_detail(rsshub_url, username, tweet_id)
            if all(tweet_id not in f"{t.get('id', '')} {t.get('link', '')}" for t in tweets):
                tweets.append(recovery_tweet)
                print(f"  Recovery: 补取到 {tweet_id}")
        except Exception as e:
            print(f"  [WARN] Recovery 补取 {tweet_id} 失败: {e}")
    print(f"  共拉到 {len(tweets)} 条")

    # 2. 去重
    sent_ids = load_sent(str(SENT_FILE))
    new_tweets = filter_new(tweets, sent_ids)
    print(f"[2/4] 去重后新推文 {len(new_tweets)} 条")

    if not new_tweets:
        print("[完成] 无新推文")
        return

    # 3. 分类 + 关键词兜底 + 推送
    print("[3/4] 分类并推送...")
    pushed = 0
    for t in new_tweets:
        # 关键词先判断；明确含 reset 时不等待、也不消耗 LLM 调用。
        keyword_hit = contains_reset(t)
        llm_result = None
        if not keyword_hit and deepseek_key:
            try:
                llm_result = classify(t, deepseek_key, deepseek_model)
            except Exception as e:
                print(f"  [WARN] LLM 分类失败 {t['id']}: {e}")

        # LLM 判定
        llm_push = False
        cat = conf = reason = None
        if llm_result:
            cat = llm_result.get("category", 3)
            conf = llm_result.get("confidence", 0)
            reason = llm_result.get("reason", "")
            if cat in (1, 2) and conf >= threshold:
                llm_push = True

        # 推送条件：LLM 判定 OR 关键词命中
        should_push = llm_push or keyword_hit

        if should_push:
            # 构造标签，标注是哪条线触发的推送
            if llm_push and keyword_hit:
                llm_label = "明确" if cat == 1 else "暗示"
                tag = f"LLM:{llm_label}({conf:.2f}) + 关键词命中"
            elif llm_push:
                llm_label = "明确" if cat == 1 else "暗示"
                tag = f"LLM:{llm_label}({conf:.2f})"
            else:
                # 关键词命中但 LLM 判无关（或 LLM 失败）
                tag = "关键词命中"

            title = f"Tibo Codex Reset 信号 [{tag}]"
            # 完整展示推文原文（清理 HTML 标签）+ 发布时间
            raw_text = strip_html(t.get("summary", "") or t.get("title", ""))
            pub_time = format_time(t.get("published", ""))
            content = f"发布时间：{pub_time}\n\n推文原文：\n{raw_text}"
            if reason:
                content += f"\n\nLLM 分析：{reason}"

            # 推送（飞书 + 微信，任一成功即计数）
            feishu_ok = wechat_ok = False
            if feishu_webhook:
                feishu_ok = feishu_push(feishu_webhook, title, content, t.get("link", ""))
                print(f"  飞书推送 {t['id']}: {tag} -> {'OK' if feishu_ok else 'FAIL'}")
            else:
                print(f"  [SKIP飞书，未配 webhook] {t['id']}: {tag}")

            if serverchan_key:
                wechat_ok = wechat_push(serverchan_key, title, content, t.get("link", ""))
                print(f"  微信推送 {t['id']}: {tag} -> {'OK' if wechat_ok else 'FAIL'}")
            else:
                print(f"  [SKIP微信，未配 SERVERCHAN_KEY] {t['id']}: {tag}")

            if feishu_ok or wechat_ok:
                pushed += 1
        else:
            conf_str = f"{conf:.2f}" if conf is not None else "N/A"
            print(f"  跳过 {t['id']}: cat={cat} conf={conf_str} ({reason or '无LLM分析'})")

        # 需要推送的帖子只有至少一个渠道成功后才标记，避免通知失败却永久丢失。
        if not should_push or feishu_ok or wechat_ok:
            sent_ids.add(t["id"])
        else:
            print(f"  [WARN] {t['id']} 所有通知渠道均失败，下次将重试")

    # 4. 持久化
    print("[4/4] 保存已处理记录...")
    save_sent(str(SENT_FILE), sent_ids)
    print(f"[完成] 推送 {pushed} 条，共处理 {len(new_tweets)} 条新推文")


if __name__ == "__main__":
    main()
