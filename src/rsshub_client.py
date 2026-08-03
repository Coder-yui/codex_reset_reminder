"""RSSHub 客户端：从自建 RSSHub 拉取 Tibo 的 X 时间线 RSS"""
import requests
import feedparser
from typing import List, Dict


def fetch_tweets(rsshub_url: str, username: str, timeout: int = 30) -> List[Dict]:
    """
    从 RSSHub 拉取指定 X 用户的最近推文。

    Args:
        rsshub_url: RSSHub 实例根地址，如 https://xxx.onrender.com
        username: X 用户名（不带 @）
        timeout: HTTP 请求超时秒数

    Returns:
        推文列表，每条包含 id / title / link / summary / published 字段。
        列表顺序与 RSS 中的顺序一致（通常是新→旧）。
    """
    url = f"{rsshub_url.rstrip('/')}/twitter/user/{username}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    tweets: List[Dict] = []
    for entry in feed.entries:
        # RSSHub 的 twitter/user 路由一般会带 guid/link，作为去重 id
        tweet_id = entry.get("id") or entry.get("guid") or entry.get("link", "")
        tweets.append({
            "id": tweet_id,
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", ""),
            "published": entry.get("published", ""),
        })
    return tweets
