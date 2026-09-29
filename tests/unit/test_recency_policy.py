from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from app.config import load_recency_policy
from app.recency import (
    backfill_cutoff_date, posting_freshness_label, posting_is_recent, recency_cutoff_date,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class RecencyPolicyTest(unittest.TestCase):
    def test_backfill_window_is_distinct_and_configurable_without_narrowing_browse(self) -> None:
        policy = load_recency_policy()
        now = datetime(2026, 9, 28, 23, 59, tzinfo=timezone.utc)
        self.assertEqual(policy.backfill_max_age_days, 14)
        self.assertEqual(backfill_cutoff_date(policy, now=now), "2026-09-14")
        self.assertEqual(recency_cutoff_date(policy, now=now), "2026-09-07")
        self.assertTrue(posting_is_recent({
            "posted_at": "2026-09-10", "first_seen_at": "2026-09-28",
        }, policy, now=now))
        raw = yaml.safe_load((REPO_ROOT / "config/recency_policy.yaml").read_text())
        with tempfile.TemporaryDirectory() as directory:
            for days, expected in ((0, "2026-09-28"), (7, "2026-09-21"), (21, "2026-09-07")):
                with self.subTest(days=days):
                    path = Path(directory) / f"recency-{days}.yaml"
                    path.write_text(yaml.safe_dump(raw | {"backfill_max_age_days": days}))
                    configured = load_recency_policy(path)
                    self.assertEqual(backfill_cutoff_date(configured, now=now), expected)
                    self.assertEqual(recency_cutoff_date(configured, now=now), "2026-09-07")

    def test_backfill_window_rejects_nonintegers_negative_and_wider_than_browse(self) -> None:
        raw = yaml.safe_load((REPO_ROOT / "config/recency_policy.yaml").read_text())
        with tempfile.TemporaryDirectory() as directory:
            for index, value in enumerate((None, True, False, 14.0, "14", -1, 22)):
                with self.subTest(value=value):
                    path = Path(directory) / f"invalid-{index}.yaml"
                    path.write_text(yaml.safe_dump(raw | {"backfill_max_age_days": value}))
                    with self.assertRaisesRegex(ValueError, "backfill_max_age_days"):
                        load_recency_policy(path)
            path = Path(directory) / "missing.yaml"
            del raw["backfill_max_age_days"]
            path.write_text(yaml.safe_dump(raw))
            with self.assertRaisesRegex(ValueError, "backfill_max_age_days"):
                load_recency_policy(path)

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
        self.assertEqual(
            posting_freshness_label(
                {"posted_at": "2026-07-08", "first_seen_at": "2026-07-09"},
                now=now,
            ),
            "posted 3d ago",
        )
        self.assertEqual(
            posting_freshness_label(
                {"posted_at": None, "first_seen_at": "2026-07-08"},
                now=now,
            ),
            "first seen 3d ago",
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
        web_recency = (REPO_ROOT / "web" / "lib" / "recency.ts").read_text(
            encoding="utf-8"
        )
        digest = (REPO_ROOT / "app" / "services" / "digest.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("recencyCutoffDate", data_layer)
        self.assertIn('gte("effective_at", `${cutoff}T00:00:00Z`)', data_layer)
        self.assertIn('href={data.includeOlder ? "/" : "/?older=1"}', matches_ui)
        self.assertIn("freshnessLabel(role)", matches_ui)
        self.assertIn("freshnessLabel(role)", shortlist_ui)
        self.assertIn("profileConfig.recency.maxAgeDays", web_recency)
        self.assertIn("posting_freshness_label(row)", digest)
