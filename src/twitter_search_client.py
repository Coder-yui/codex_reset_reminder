"""使用登录 Cookie 调用 X 的 Latest Search 时间线作为免费补源。"""

import json
import re
import time
from datetime import datetime
from email.utils import format_datetime
from typing import Dict, Iterator, List, Optional
from urllib.parse import urljoin

import requests


BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
API_DOC_URL = (
    "https://cdn.jsdelivr.net/gh/fa0311/TwitterInternalAPIDocument"
    "@master/docs/json/API.json"
)
FALLBACK_QUERY_ID = "BGd0T_j7oVwlW5U79tO_0A"
FALLBACK_FEATURES = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}


def _walk(value) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _screen_name(result: dict) -> str:
    user = (
        result.get("core", {})
        .get("user_results", {})
        .get("result", {})
    )
    return (user.get("core", {}).get("screen_name") or user.get("legacy", {}).get("screen_name") or "")


def _published(created_at: str) -> str:
    if not created_at:
        return ""
    try:
        parsed = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return format_datetime(parsed)
    except ValueError:
        return created_at


def parse_search(data: dict, username: str) -> List[Dict]:
    """从 SearchTimeline 响应中提取目标用户自己发布的帖子。"""
    tweets: Dict[str, Dict] = {}
    expected = username.lower()
    for node in _walk(data):
        result = (node.get("tweet_results") or {}).get("result")
        if not isinstance(result, dict):
            continue
        if isinstance(result.get("tweet"), dict):
            result = result["tweet"]
        if _screen_name(result).lower() != expected:
            continue

        tweet_id = result.get("rest_id")
        legacy = result.get("legacy") or {}
        note = (
            result.get("note_tweet", {})
            .get("note_tweet_results", {})
            .get("result", {})
        )
        text = note.get("text") or legacy.get("full_text") or ""
        if not tweet_id or not text:
            continue
        tweets[tweet_id] = {
            "id": f"https://twitter.com/{username}/status/{tweet_id}",
            "title": text[:150].replace("\n", " "),
            "link": f"https://x.com/{username}/status/{tweet_id}",
            "summary": text,
            "published": _published(legacy.get("created_at", "")),
        }
    if not tweets:
        raise ValueError("X Latest Search 没有解析到目标用户帖子")
    return sorted(tweets.values(), key=lambda tweet: tweet["id"], reverse=True)


def _operation_config(timeout: int) -> tuple[str, dict]:
    try:
        response = requests.get(API_DOC_URL, timeout=timeout)
        response.raise_for_status()
        operation = response.json()["graphql"]["SearchTimeline"]
        return operation["queryId"], operation["features"]
    except Exception:
        return FALLBACK_QUERY_ID, FALLBACK_FEATURES


def _extract_search_query_id(script: str) -> Optional[str]:
    """从 X 的前端 bundle 中提取 SearchTimeline 的当前 operation ID。"""
    patterns = (
        r'queryId:\s*["\']([^"\']+)["\']\s*,\s*operationName:\s*["\']SearchTimeline["\']',
        r'operationName:\s*["\']SearchTimeline["\']\s*,\s*queryId:\s*["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, script)
        if match:
            return match.group(1)
    return None


def _resolve_query_id_from_x(
    auth_token: str, ct0: str, username: str, timeout: int
) -> Optional[str]:
    """固定 ID 失效时，从登录后的 X 搜索页 bundle 动态解析当前 ID。"""
    page_url = f"https://x.com/search?q=from%3A{username}&src=typed_query&f=live"
    cookies = {"auth_token": auth_token, "ct0": ct0}
    headers = {
        "accept": "text/html,application/xhtml+xml",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/139.0 Safari/537.36",
    }
    page = requests.get(page_url, headers=headers, cookies=cookies, timeout=timeout)
    page.raise_for_status()
    script_urls = [
        urljoin(page_url, src)
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', page.text)
    ]
    # Search 专用 chunk 最可能包含 operation；main 是常见兜底。限制数量避免过量请求。
    preferred = [url for url in script_urls if "Search" in url or "/main." in url]
    remaining = [url for url in script_urls if url not in preferred]
    for script_url in (preferred + remaining)[:30]:
        response = requests.get(script_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        query_id = _extract_search_query_id(response.text)
        if query_id:
            return query_id
    return None


def fetch_tweets(
    auth_token: str,
    ct0: str,
    username: str,
    timeout: int = 30,
    retries: int = 1,
    retry_delay: int = 3,
) -> List[Dict]:
    """搜索 `from:<username>` 的最新结果。"""
    if not auth_token or not ct0:
        raise ValueError("TWITTER_AUTH_TOKEN/TWITTER_CT0 未配置")
    query_id, features = _operation_config(timeout)
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {BEARER_TOKEN}",
        "content-type": "application/json",
        "referer": f"https://x.com/search?q=from%3A{username}&src=typed_query&f=live",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/139.0 Safari/537.36",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
    }
    params = {
        "variables": json.dumps(
            {
                "rawQuery": f"from:{username}",
                "count": 20,
                "querySource": "typed_query",
                "product": "Latest",
            },
            separators=(",", ":"),
        ),
        "features": json.dumps(features, separators=(",", ":")),
    }
    last_error: Optional[Exception] = None
    # 外部 API 文档可能晚于 X 前端更新；依次尝试文档值、内置值和网页实时值。
    query_ids = list(dict.fromkeys((query_id, FALLBACK_QUERY_ID)))

    def try_query(candidate_id: str) -> Optional[List[Dict]]:
        nonlocal last_error
        url = f"https://x.com/i/api/graphql/{candidate_id}/SearchTimeline"
        for attempt in range(retries + 1):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    cookies={"auth_token": auth_token, "ct0": ct0},
                    params=params,
                    timeout=timeout,
                )
                response.raise_for_status()
                return parse_search(response.json(), username)
            except Exception as error:
                last_error = error
                if attempt < retries:
                    time.sleep(retry_delay)
        return None

    for candidate_id in query_ids:
        result = try_query(candidate_id)
        if result is not None:
            return result

    try:
        live_query_id = _resolve_query_id_from_x(auth_token, ct0, username, timeout)
        if live_query_id and live_query_id not in query_ids:
            result = try_query(live_query_id)
            if result is not None:
                return result
    except Exception as error:
        last_error = error
    raise RuntimeError(f"X Latest Search 拉取失败: {last_error}") from last_error
