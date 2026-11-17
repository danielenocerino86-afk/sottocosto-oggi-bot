"""Regression tests for the repost policy."""
import unittest
from unittest.mock import patch
import bot


class RepostPolicyTests(unittest.TestCase):
    def setUp(self):
        self.deal = {"asin": "B012345678", "current_price": 90.0}
        self.previous = {"price": 100.0, "ts": "2026-11-16", "days_ago": 1}

    def check(self, new_price):
        self.deal["current_price"] = new_price
        with patch.object(bot, "get_posted_info", return_value=self.previous):
            return bot.should_skip_repost({}, self.deal)

    def test_price_drop_reposts(self):
        skip, reason = self.check(90.0)
        self.assertFalse(skip)
        self.assertIn("price_changed", reason)

    def test_price_increase_does_not_repost(self):
        skip, _ = self.check(110.0)
        self.assertTrue(skip)

    def test_small_price_drop_does_not_repost(self):
        skip, _ = self.check(97.0)
        self.assertTrue(skip)

    def test_first_time_reposts(self):
        with patch.object(bot, "get_posted_info", return_value=None):
            skip, reason = bot.should_skip_repost({}, self.deal)
        self.assertFalse(skip)
        self.assertEqual(reason, "first_time")


if __name__ == "__main__":
    unittest.main()
