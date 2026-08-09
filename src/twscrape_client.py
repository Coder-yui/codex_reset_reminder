"""使用 twscrape 的 UserTweetsAndReplies 读取 Tibo 的完整时间线。"""

import asyncio
import tempfile
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List

from twscrape import API, gather


async def _fetch(
    auth_token: str,
    ct0: str,
    username: str,
    user_id: str,
    limit: int,
) -> List[Dict]:
    with tempfile.TemporaryDirectory(prefix="tibo-monitor-") as temp_dir:
        api = API(str(Path(temp_dir) / "accounts.db"), raise_when_no_account=True)
        cookies = f"auth_token={auth_token}; ct0={ct0}"
        await api.pool.add_account_cookies("monitor", cookies)
        results = await gather(api.user_tweets_and_replies(int(user_id), limit=limit))

    tweets: List[Dict] = []
    expected = username.lower()
    seen = set()
    for tweet in results:
        if not tweet.user or tweet.user.username.lower() != expected:
            continue
        status_id = str(tweet.id)
        if status_id in seen:
            continue
        seen.add(status_id)
        tweets.append(
            {
                "id": f"https://twitter.com/{username}/status/{status_id}",
                "status_id": status_id,
                "title": tweet.rawContent[:150].replace("\n", " "),
                "summary": tweet.rawContent,
                "link": tweet.url,
                "published": format_datetime(tweet.date),
            }
        )
    return tweets


def fetch_tweets(
    auth_token: str,
    ct0: str,
    username: str,
    user_id: str,
    limit: int = 40,
) -> List[Dict]:
    """同步入口：只调用 UserTweetsAndReplies 这一种 X 时间线。"""
    return asyncio.run(_fetch(auth_token, ct0, username, user_id, limit))
