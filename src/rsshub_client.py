"""RSSHub 客户端：从自建 RSSHub 拉取 Tibo 的 X 时间线 RSS"""
import time
import requests
import feedparser
from typing import List, Dict


def fetch_tweets(rsshub_url: str, username: str, timeout: int = 60,
                 retries: int = 2, retry_delay: int = 5) -> List[Dict]:
    """
    从 RSSHub 拉取指定 X 用户的最近推文。

    Args:
        rsshub_url: RSSHub 实例根地址，如 https://xxx.onrender.com
        username: X 用户名（不带 @）
        timeout: 单次 HTTP 请求超时秒数。Render 免费实例长时间无请求后会
                 休眠，冷启动需 25-30s，默认 60s 留足余量。
        retries: 失败重试次数。冷启动导致首次超时后，第二次请求通常很快返回。
        retry_delay: 重试间隔秒数。

    Returns:
        推文列表，每条包含 id / title / link / summary / published 字段。
        列表顺序与 RSS 中的顺序一致（通常是新→旧）。
    """
    url = f"{rsshub_url.rstrip('/')}/twitter/user/{username}"
    last_err = None
    for attempt in range(retries + 1):
        try:
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
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                print(f"  [WARN] 拉取失败（第{attempt + 1}次），{retry_delay}s 后重试: {e}")
                time.sleep(retry_delay)
            else:
                print(f"  [WARN] 拉取失败（第{attempt + 1}次，已达重试上限）: {e}")
    raise last_err
