from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from app.config import load_recency_policy
from app.recency import posting_is_recent, recency_cutoff_date


REPO_ROOT = Path(__file__).resolve().parents[2]


class RecencyPolicyTest(unittest.TestCase):
    def test_policy_defaults_to_21_days_and_falls_back_to_first_seen(self) -> None:
        policy = load_recency_policy()
        now = datetime(2026, 7, 11, tzinfo=timezone.utc)
        self.assertEqual(policy.max_age_days, 21)
        self.assertEqual(recency_cutoff_date(policy, now=now), "2026-06-20")
        self.assertTrue(
            posting_is_recent(
                {"posted_at": None, "first_seen_at": "2026-06-21T12:00:00+00:00"},
                policy,
                now=now,
            )
        )
        self.assertFalse(
            posting_is_recent(
                {"posted_at": None, "first_seen_at": "2026-06-19T12:00:00+00:00"},
                policy,
                now=now,
            )
        )

    def test_generated_web_config_and_ui_share_recency_policy(self) -> None:
        generated = json.loads(
            (REPO_ROOT / "web" / "generated" / "profile-config.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(generated["recency"]["maxAgeDays"], load_recency_policy().max_age_days)
        data_layer = (REPO_ROOT / "web" / "lib" / "data" / "calibrated-evaluations.ts").read_text(
            encoding="utf-8"
        )
        matches_ui = (REPO_ROOT / "web" / "app" / "potential-matches-client.tsx").read_text(
            encoding="utf-8"
        )
        shortlist_ui = (REPO_ROOT / "web" / "app" / "to-apply" / "to-apply-client.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("recencyCutoffDate", data_layer)
        self.assertIn("posted_at.gte.${cutoff}", data_layer)
        self.assertIn("posted_at.is.null,first_seen_at.gte.${cutoff}", data_layer)
        self.assertIn('href={data.includeOlder ? "/" : "/?older=1"}', matches_ui)
        self.assertIn("freshnessLabel(role)", matches_ui)
        self.assertIn("freshnessLabel(role)", shortlist_ui)
