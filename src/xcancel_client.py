"""从 XCancel 的公开用户主页读取最近帖子。"""

import re
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
)
STATUS_PATH_RE = re.compile(r"^/([^/]+)/status/(\d+)")


def _parse_published(value: str) -> str:
    """把 XCancel 的 UTC 时间转换为 RSS 风格的 RFC822 时间。"""
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value.replace(" · ", " "), "%b %d, %Y %I:%M %p UTC")
        return format_datetime(parsed.replace(tzinfo=timezone.utc), usegmt=True)
    except ValueError:
        return value


def parse_profile(html: str, username: str) -> List[Dict]:
    """解析 XCancel 用户主页，只保留该用户自己发布的帖子。"""
    soup = BeautifulSoup(html, "html.parser")
    timeline_items = soup.select("div.timeline-item[data-username]")
    if not timeline_items:
        raise ValueError("XCancel 页面中没有找到时间线，可能被限流或页面结构已变化")

    tweets: List[Dict] = []
    expected_username = username.lower()
    for item in timeline_items:
        if (item.get("data-username") or "").lower() != expected_username:
            continue

        link_element = item.select_one("a.tweet-link[href]")
        href = link_element.get("href", "") if link_element else ""
        match = STATUS_PATH_RE.match(href)
        if not match:
            continue

        screen_name, tweet_id = match.groups()
        content_element = item.select_one("div.tweet-content")
        content = content_element.get_text("\n", strip=True) if content_element else ""
        if not content:
            content = "[无文字内容]"

        date_element = item.select_one("span.tweet-date a[title]")
        published = _parse_published(date_element.get("title", "") if date_element else "")
        link = f"https://x.com/{screen_name}/status/{tweet_id}"
        tweets.append(
            {
                "id": f"https://twitter.com/{screen_name}/status/{tweet_id}",
                "title": content[:150].replace("\n", " "),
                "link": link,
                "summary": content,
                "published": published,
            }
        )

    if not tweets:
        raise ValueError(f"XCancel 页面中没有解析到 @{username} 的帖子")
    return tweets


def fetch_tweets(
    base_url: str,
    username: str,
    timeout: int = 30,
    retries: int = 2,
    retry_delay: int = 3,
) -> List[Dict]:
    """请求 XCancel 公开主页并返回与 RSSHub 客户端一致的数据结构。"""
    url = urljoin(f"{base_url.rstrip('/')}/", username)
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            response.raise_for_status()
            return parse_profile(response.text, username)
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(retry_delay)
    raise RuntimeError(f"XCancel 拉取失败: {last_error}") from last_error
