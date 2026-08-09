"""并行读取多个帖子来源，并按 X 帖子 ID 合并。"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Tuple

from rsshub_client import fetch_tweets as fetch_from_rsshub
from xcancel_client import fetch_tweets as fetch_from_xcancel


STATUS_ID_RE = re.compile(r"(?:status/)?(\d{10,})")


def _status_id(tweet: Dict) -> str:
    """从 id/link 中提取稳定的数字帖子 ID。"""
    for value in (tweet.get("link", ""), tweet.get("id", "")):
        match = STATUS_ID_RE.search(str(value))
        if match:
            return match.group(1)
    return str(tweet.get("id", ""))


def merge_tweets(groups: Iterable[List[Dict]]) -> List[Dict]:
    """对多个来源取并集；重复时优先保留正文更完整的版本。"""
    merged: Dict[str, Dict] = {}
    for tweets in groups:
        for tweet in tweets:
            key = _status_id(tweet)
            if not key:
                continue
            current = merged.get(key)
            if current is None or len(tweet.get("summary", "")) > len(current.get("summary", "")):
                merged[key] = tweet

    def sort_key(tweet: Dict) -> Tuple[int, str]:
        status_id = _status_id(tweet)
        return (int(status_id) if status_id.isdigit() else 0, status_id)

    return sorted(merged.values(), key=sort_key, reverse=True)


def fetch_tweets(rsshub_url: str, xcancel_url: str, username: str) -> List[Dict]:
    """并行读取已配置的数据源；任一成功即可，全部失败才报错。"""
    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        if rsshub_url:
            jobs[executor.submit(fetch_from_rsshub, rsshub_url, username)] = "RSSHub"
        if xcancel_url:
            jobs[executor.submit(fetch_from_xcancel, xcancel_url, username)] = "XCancel"

        if not jobs:
            raise ValueError("RSSHUB_URL 和 XCANCEL_URL 至少需要配置一个")

        successful_groups: List[List[Dict]] = []
        errors = []
        for future in as_completed(jobs):
            source = jobs[future]
            try:
                tweets = future.result()
                successful_groups.append(tweets)
                print(f"  {source}: {len(tweets)} 条")
            except Exception as error:
                errors.append(f"{source}: {error}")
                print(f"  [WARN] {source} 失败: {error}")

    if not successful_groups:
        raise RuntimeError("所有推文来源均失败：" + "; ".join(errors))
    return merge_tweets(successful_groups)
