import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from multi_source_client import fetch_tweets, merge_tweets
from xcancel_client import parse_profile


PROFILE_HTML = """
<div class="timeline-item" data-username="thsottiaux">
  <a class="tweet-link" href="/thsottiaux/status/2086188036493344823#m"></a>
  <div class="tweet-content media-body">
    I have reset usage limits for all paid users of ChatGPT Work and Codex.
  </div>
  <span class="tweet-date">
    <a title="Aug 8, 2026 · 8:29 PM UTC"></a>
  </span>
</div>
<div class="timeline-item" data-username="someone_else">
  <a class="tweet-link" href="/someone_else/status/2086189000000000000#m"></a>
  <div class="tweet-content">A reply from somebody else</div>
</div>
"""


class XCancelParserTests(unittest.TestCase):
    def test_parses_target_post_and_ignores_other_users(self):
        tweets = parse_profile(PROFILE_HTML, "thsottiaux")

        self.assertEqual(len(tweets), 1)
        self.assertEqual(
            tweets[0]["id"],
            "https://twitter.com/thsottiaux/status/2086188036493344823",
        )
        self.assertIn("reset usage limits", tweets[0]["summary"])
        self.assertEqual(tweets[0]["published"], "Sat, 08 Aug 2026 20:29:00 GMT")

    def test_rejects_non_timeline_response(self):
        with self.assertRaisesRegex(ValueError, "没有找到时间线"):
            parse_profile("<html><body>rate limited</body></html>", "thsottiaux")


class MultiSourceTests(unittest.TestCase):
    def test_merge_is_union_and_prefers_richer_duplicate(self):
        rsshub = [
            {
                "id": "https://twitter.com/thsottiaux/status/10000000001",
                "link": "https://x.com/thsottiaux/status/10000000001",
                "summary": "short",
            }
        ]
        xcancel = [
            {
                "id": "https://twitter.com/thsottiaux/status/10000000001",
                "link": "https://x.com/thsottiaux/status/10000000001",
                "summary": "a more complete duplicate",
            },
            {
                "id": "https://twitter.com/thsottiaux/status/10000000002",
                "link": "https://x.com/thsottiaux/status/10000000002",
                "summary": "only in backup source",
            },
        ]

        merged = merge_tweets([rsshub, xcancel])

        self.assertEqual([tweet["summary"] for tweet in merged], [
            "only in backup source",
            "a more complete duplicate",
        ])

    @patch("multi_source_client.fetch_from_xcancel")
    @patch("multi_source_client.fetch_from_rsshub")
    def test_one_source_failure_does_not_abort(self, rsshub_fetch, xcancel_fetch):
        rsshub_fetch.side_effect = RuntimeError("RSSHub unavailable")
        xcancel_fetch.return_value = [
            {
                "id": "https://twitter.com/thsottiaux/status/2086188036493344823",
                "link": "https://x.com/thsottiaux/status/2086188036493344823",
                "summary": "reset usage limits",
            }
        ]

        tweets = fetch_tweets("https://rsshub.example", "https://xcancel.com", "thsottiaux")

        self.assertEqual(len(tweets), 1)
        self.assertIn("2086188036493344823", tweets[0]["id"])

    @patch("multi_source_client.fetch_from_xcancel")
    @patch("multi_source_client.fetch_from_rsshub")
    def test_all_sources_failure_is_reported(self, rsshub_fetch, xcancel_fetch):
        rsshub_fetch.side_effect = RuntimeError("RSSHub unavailable")
        xcancel_fetch.side_effect = RuntimeError("XCancel unavailable")

        with self.assertRaisesRegex(RuntimeError, "所有推文来源均失败"):
            fetch_tweets("https://rsshub.example", "https://xcancel.com", "thsottiaux")


if __name__ == "__main__":
    unittest.main()
