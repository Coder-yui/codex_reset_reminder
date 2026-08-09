import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from main import contains_reset
from twscrape_client import fetch_tweets


class ResetDetectionTests(unittest.TestCase):
    def test_matches_reset_case_insensitively(self):
        self.assertTrue(contains_reset({"summary": "I have RESET usage limits"}))

    def test_ignores_unrelated_post(self):
        self.assertFalse(contains_reset({"summary": "Codex is available"}))


class TwscrapeClientTests(unittest.TestCase):
    @patch("twscrape_client._fetch", new_callable=AsyncMock)
    def test_sync_entry_uses_single_timeline_fetch(self, async_fetch):
        async_fetch.return_value = [{"status_id": "2086188036493344823"}]

        tweets = fetch_tweets("token", "csrf", "thsottiaux", "1953337039510003712")

        self.assertEqual(tweets[0]["status_id"], "2086188036493344823")
        async_fetch.assert_awaited_once_with(
            "token", "csrf", "thsottiaux", "1953337039510003712", 40
        )


if __name__ == "__main__":
    unittest.main()
