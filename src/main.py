"""监控 Tibo 的 X 时间线，命中 reset 后推送飞书和微信。"""

import os
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from deduper import filter_new, load_sent, save_sent
from feishu_pusher import push as feishu_push
from twscrape_client import fetch_tweets
from wechat_pusher import push as wechat_push


SENT_FILE = Path(__file__).parent / "sent_tweets.json"


def contains_reset(tweet: dict) -> bool:
    return "reset" in tweet.get("summary", "").lower()


def format_time(pub_date: str) -> str:
    if not pub_date:
        return "未知时间"
    try:
        from datetime import timedelta, timezone

        cst = parsedate_to_datetime(pub_date).astimezone(
            timezone(timedelta(hours=8))
        )
        return cst.strftime("%Y-%m-%d %H:%M") + " (北京时间)"
    except Exception:
        return pub_date


def main() -> None:
    load_dotenv()

    username = os.getenv("TWITTER_USERNAME") or "thsottiaux"
    user_id = os.getenv("TWITTER_USER_ID") or "1953337039510003712"
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "")
    ct0 = os.getenv("TWITTER_CT0", "")
    feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    serverchan_key = os.getenv("SERVERCHAN_KEY", "")

    if not auth_token or not ct0:
        raise RuntimeError("TWITTER_AUTH_TOKEN 和 TWITTER_CT0 必须配置")
    if not feishu_webhook and not serverchan_key:
        raise RuntimeError("至少配置 FEISHU_WEBHOOK_URL 或 SERVERCHAN_KEY")

    print(f"[1/4] 通过 twscrape 拉取 @{username} 的 Tweets & Replies...")
    tweets = fetch_tweets(auth_token, ct0, username, user_id)
    print(f"  拉到 {len(tweets)} 条")
    print("  帖子 IDs: " + ", ".join(tweet["status_id"] for tweet in tweets))

    sent_ids = load_sent(str(SENT_FILE))
    new_tweets = filter_new(tweets, sent_ids)
    print(f"[2/4] 去重后新帖子 {len(new_tweets)} 条")

    pushed = 0
    print("[3/4] 检查 reset 并推送...")
    for tweet in new_tweets:
        should_push = contains_reset(tweet)
        delivered = False

        if should_push:
            title = "Tibo Codex Reset 信号"
            content = (
                f"发布时间：{format_time(tweet.get('published', ''))}\n\n"
                f"推文原文：\n{tweet.get('summary', '')}"
            )
            if feishu_webhook:
                ok = feishu_push(feishu_webhook, title, content, tweet["link"])
                delivered = delivered or ok
                print(f"  飞书推送 {tweet['status_id']}: {'OK' if ok else 'FAIL'}")
            if serverchan_key:
                ok = wechat_push(serverchan_key, title, content, tweet["link"])
                delivered = delivered or ok
                print(f"  微信推送 {tweet['status_id']}: {'OK' if ok else 'FAIL'}")
            if delivered:
                pushed += 1
            else:
                print(f"  [WARN] {tweet['status_id']} 推送失败，下次继续重试")
        else:
            print(f"  跳过 {tweet['status_id']}: 未命中 reset")

        if not should_push or delivered:
            sent_ids.add(tweet["id"])

    print("[4/4] 保存去重记录...")
    save_sent(str(SENT_FILE), sent_ids)
    print(f"[完成] 推送 {pushed} 条，共处理 {len(new_tweets)} 条新帖子")


if __name__ == "__main__":
    main()
