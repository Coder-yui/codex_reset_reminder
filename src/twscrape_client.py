"""使用 twscrape 的 UserTweetsAndReplies 读取 Tibo 的完整时间线。"""

import asyncio
import tempfile
import time
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List

from twscrape import API, gather


DEFAULT_FETCH_LIMIT = 5


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
        results = await gather(
            api.user_tweets_and_replies(
                int(user_id),
                limit=limit,
                kv={"count": limit},
            )
        )

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
    limit: int = DEFAULT_FETCH_LIMIT,
    max_retries: int = 3,
) -> List[Dict]:
    """同步入口：只调用 UserTweetsAndReplies 这一种 X 时间线。

    每次最多抓取 5 条，并将单次 GraphQL 请求的 count 同样限制为 5，降低被 X 拒绝的概率。
    X 的接口偶发抖动，失败时按指数退避重试几次，避免单次网络波动导致整个 workflow 标红。
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return asyncio.run(_fetch(auth_token, ct0, username, user_id, limit))
        except Exception as exc:
            last_exc = exc
            print(
                f"[twscrape] 第 {attempt}/{max_retries} 次抓取失败: {type(exc).__name__}: {exc}",
                flush=True,
            )
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    # 全部重试耗尽，抛出最后一次异常
    raise RuntimeError(
        f"抓取 @{username} 时间线连续失败 {max_retries} 次，最后错误: "
        f"{type(last_exc).__name__}: {last_exc}"
    ) from last_exc
