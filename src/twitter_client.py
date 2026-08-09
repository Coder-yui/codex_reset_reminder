"""X/Twitter 直接拉取：用 auth_token + ct0 cookie 调 X GraphQL API

相比 RSSHub 的优势：
- 走 UserTweetsAndReplies endpoint，能拿到 Tibo 的所有原创 + 引用 + 回复推文
- 不依赖 RSSHub 镜像更新，不被 RSSHub 自己的过滤/截断逻辑影响

认证要素（与 RSSHub web-api 一致）：
- Cookie: auth_token + ct0
- Authorization: Bearer <X web 公开 token>
- x-csrf-token: <ct0 的值>（必须与 cookie 一致）
"""
import json
import re
import time
from typing import List, Dict, Optional

import requests


# X web client 公开 Bearer token（所有未登录用户共用）
# 注：等价于 RSSHub 内置的同一值
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# GraphQL queryId 兜底值。Twitter 偶尔更新这些 ID，常规路径会先从
# GitHub mirror 拉最新值；拉取失败时回退到这里。
# 参考：DIYgod/RSSHub/lib/routes/twitter/api/web-api/gql-id-resolver.ts
FALLBACK_QUERY_IDS = {
    "UserByScreenName": "Gb-d6r0vxPOADdG62OEBpQ",
    "UserTweetsAndReplies": "wc5DRl4VaW5lSqJ8YbftZQ",
    "UserTweets": "eoJ5zbv51Z_KVl81v9PmLQ",
}

# fa0311 维护的 Twitter GraphQL queryId 文档（Twitter 改 ID 时这里会先更新）
GQL_ID_DOC_URL = (
    "https://cdn.jsdelivr.net/gh/fa0311/TwitterInternalAPIDocument"
    "@master/docs/json/API.json"
)

# UserTweetsAndReplies 的 features（与 RSSHub 一致）
FEATURES_USER_TWEETS = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

# UserByScreenName 的 features
FEATURES_USER = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}


class TwitterClient:
    """用 cookie 直接调 X GraphQL 的客户端。

    使用方式：
        client = TwitterClient(auth_token="...", ct0="...")
        tweets = client.fetch_user_tweets_with_replies("thsottiaux", count=20)
    """

    def __init__(self, auth_token: str, ct0: str, timeout: int = 30):
        if not auth_token or not ct0:
            raise ValueError("auth_token 和 ct0 都必须提供")
        self.auth_token = auth_token
        self.ct0 = ct0
        self.timeout = timeout
        self._query_ids: Optional[Dict[str, str]] = None
        # 关键：ct0 的值必须同时作为 cookie 和 x-csrf-token header
        # 两者不一致会被 X 返回 403
        self._cookies = {
            "auth_token": auth_token,
            "ct0": ct0,
        }
        self._headers = {
            "authority": "x.com",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {BEARER_TOKEN}",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "dnt": "1",
            "pragma": "no-cache",
            "referer": "https://x.com/",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "x-csrf-token": ct0,
            "x-twitter-auth-type": "OAuth2Session",
        }

    def _ensure_query_ids(self) -> Dict[str, str]:
        """懒加载 queryId 映射：先从 GitHub mirror 拉最新，失败回退到内置值。"""
        if self._query_ids is not None:
            return self._query_ids
        try:
            resp = requests.get(GQL_ID_DOC_URL, timeout=self.timeout)
            resp.raise_for_status()
            api_doc = resp.json()
            graphql = api_doc.get("api", {}).get("graphql", {})
            self._query_ids = {
                name: entry["queryId"]
                for name, entry in graphql.items()
                if name in FALLBACK_QUERY_IDS and "queryId" in entry
            }
            # 任何缺失的 key 用 fallback 兜底
            for name, qid in FALLBACK_QUERY_IDS.items():
                self._query_ids.setdefault(name, qid)
        except Exception as e:
            print(f"  [WARN] 拉取最新 queryId 失败，使用 fallback: {e}")
            self._query_ids = dict(FALLBACK_QUERY_IDS)
        return self._query_ids

    def _graphql_get(self, endpoint: str, operation: str,
                     variables: dict, features: dict) -> dict:
        """调一次 GraphQL endpoint（GET），返回 data 字段。"""
        query_ids = self._ensure_query_ids()
        query_id = query_ids.get(operation) or FALLBACK_QUERY_IDS[operation]
        url = f"https://x.com/i/api/graphql/{query_id}/{operation}"
        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(features, separators=(",", ":")),
        }
        resp = requests.get(
            url, headers=self._headers, cookies=self._cookies,
            params=params, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_user_id(self, screen_name: str) -> str:
        """screen_name → 数字 rest_id（GraphQL UserTweetsAndReplies 要 rest_id）"""
        data = self._graphql_get(
            "", "UserByScreenName",
            variables={
                "screen_name": screen_name,
                "withSafetyModeUserFields": True,
            },
            features=FEATURES_USER,
        )
        result = (data.get("data", {}).get("user", {}).get("result") or {})
        rest_id = result.get("rest_id")
        if not rest_id:
            raise RuntimeError(
                f"无法解析 @{screen_name} 的 rest_id: {json.dumps(data)[:300]}"
            )
        return rest_id

    def fetch_user_tweets_with_replies(self, screen_name: str,
                                       count: int = 20) -> List[Dict]:
        """拉取指定用户的时间线（含原创 + 引用 + 回复），返回与 rsshub_client 兼容的格式。

        Args:
            screen_name: 不带 @ 的用户名
            count: 拉取条数（单页）

        Returns:
            List[Dict]，每条包含 id / title / link / summary / published。
        """
        user_id = self.get_user_id(screen_name)
        data = self._graphql_get(
            "", "UserTweetsAndReplies",
            variables={
                "userId": user_id,
                "count": count,
                "includePromotedContent": True,
                "withCommunity": True,
                "withVoice": True,
                "withV2Timeline": True,
            },
            features=FEATURES_USER_TWEETS,
        )
        return self._parse_timeline(data, user_id)

    @staticmethod
    def _parse_timeline(data: dict, user_id: str) -> List[Dict]:
        """从 GraphQL 响应里提取推文列表（与 RSSHub gatherLegacyFromData 行为一致）。

        处理两件事：
        1. 展开 profile-conversation- 开头的 entry（包含完整对话线程）
        2. 只保留 user_id_str == 目标 userId 的推文（过滤掉被回复者的推文）
        """
        instructions = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline_v2", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        entries: List[dict] = []
        for instr in instructions:
            if instr.get("type") != "TimelineAddEntries":
                continue
            for entry in instr.get("entries", []):
                eid = entry.get("entryId", "")
                content = entry.get("content") or {}
                if eid.startswith("profile-conversation-"):
                    # 展开对话线程
                    for item in content.get("items", []):
                        item_content = item.get("item", {}).get("itemContent") or {}
                        if item_content.get("itemType") == "TimelineTweet":
                            entries.append(item)
                elif content.get("itemType") == "TimelineTweet":
                    entries.append(content)

        tweets: List[Dict] = []
        for item in entries:
            tweet = TwitterClient._extract_tweet(item)
            if not tweet:
                continue
            # 只保留目标用户自己的推文
            if tweet.get("user_id_str") != user_id:
                continue
            tweets.append(tweet)
        return tweets

    @staticmethod
    def _extract_tweet(item: dict) -> Optional[Dict]:
        """从 TimelineTweet item 提取标准化字段（与 rsshub_client 输出格式一致）。"""
        content = item.get("itemContent") or {}
        tweet_results = (content.get("tweet_results") or {}).get("result") or {}
        if not tweet_results:
            return None

        # 兼容 note_tweet（长文推文，content 在 note_tweet 里）
        legacy = tweet_results.get("legacy") or {}
        note = tweet_results.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
        note_text = note.get("text", "")

        rest_id = tweet_results.get("rest_id")
        if not rest_id:
            return None

        # 摘要：长文优先用 note_tweet 全文
        full_text = legacy.get("full_text", "")
        if note_text:
            full_text = note_text + "\n\n" + full_text
        if not full_text:
            return None

        # 时间
        created_at = legacy.get("created_at", "")  # RFC822 格式 "Sat Aug 09 04:29:22 +0000 2026"
        # 转成 RSS 风格的 RFC822（feedparser 能解析的）
        published = TwitterClient._normalize_pubdate(created_at)

        # 链接
        screen_name = (
            legacy.get("user_id_str") and
            (tweet_results.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name", ""))
        )
        # 上面拿不到 screen_name 时，从 user_id 推不出来，只能从原始数据找
        user_results = tweet_results.get("core", {}).get("user_results", {}).get("result", {})
        user_legacy = user_results.get("legacy") or {}
        screen_name = user_legacy.get("screen_name", "")
        user_id_str = user_legacy.get("id_str", "")

        link = f"https://x.com/{screen_name}/status/{rest_id}" if screen_name else ""

        return {
            "id": f"https://twitter.com/{screen_name}/status/{rest_id}" if screen_name else rest_id,
            "title": full_text[:120].replace("\n", " "),
            "link": link,
            "summary": full_text,
            "published": published,
            "user_id_str": user_id_str,
        }

    @staticmethod
    def _normalize_pubdate(created_at: str) -> str:
        """X 的 created_at (如 'Sat Aug 09 04:29:22 +0000 2026') → RFC822 (email.utils 友好)。

        失败时返回原串。
        """
        if not created_at:
            return ""
        m = re.match(
            r"^[A-Z][a-z]{2}\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+"
            r"(\d{2}):(\d{2}):(\d{2})\s+([+-]\d{4})\s+(\d{4})$",
            created_at,
        )
        if not m:
            return created_at
        mon, day, hh, mm, ss, tz, year = m.groups()
        months = {
            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
            "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
            "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
        }
        mon_num = months.get(mon, "01")
        return f"{mon_num}/{day[1:] if day.startswith('0') else day}/{year} {hh}:{mm}:{ss} {tz}"


def fetch_tweets(auth_token: str, ct0: str, screen_name: str,
                 timeout: int = 30, retries: int = 2,
                 retry_delay: int = 5) -> List[Dict]:
    """便捷函数：拉取指定用户的含回复时间线。

    对应 rsshub_client.fetch_tweets 的接口（仅缺 base_url 入参），
    方便 main.py 替换时改动最小。
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            client = TwitterClient(auth_token, ct0, timeout=timeout)
            return client.fetch_user_tweets_with_replies(screen_name, count=20)
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"  [WARN] Twitter 拉取失败（第{attempt + 1}次），{retry_delay}s 后重试: {e}")
                time.sleep(retry_delay)
            else:
                print(f"  [WARN] Twitter 拉取失败（第{attempt + 1}次，已达重试上限）: {e}")
    raise last_err
