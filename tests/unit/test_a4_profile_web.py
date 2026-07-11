from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


class ProfileConfigContractTest(unittest.TestCase):
    def test_generated_profile_matches_authoritative_configs(self) -> None:
        candidate = yaml.safe_load(
            (REPO_ROOT / "config" / "candidate_profile.yaml").read_text(encoding="utf-8")
        )
        locations = yaml.safe_load(
            (REPO_ROOT / "config" / "location_policy.yaml").read_text(encoding="utf-8")
        )
        scoring = yaml.safe_load(
            (REPO_ROOT / "config" / "scoring_policy.yaml").read_text(encoding="utf-8")
        )
        watchlist = yaml.safe_load(
            (REPO_ROOT / "config" / "watchlist.yaml").read_text(encoding="utf-8")
        )
        generated = json.loads(
            (REPO_ROOT / "web" / "generated" / "profile-config.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(generated["targetRoleFamilies"], candidate["primary_role_families"])
        self.assertEqual(
            generated["approvedStretchFamilies"], candidate["approved_stretch_families"]
        )
        self.assertEqual(
            {item["name"]: item["level"] for item in generated["languages"]},
            candidate["languages"],
        )
        self.assertEqual(
            generated["locations"]["allowedMetros"],
            locations["profile_display"]["allowed_metros"],
        )
        self.assertEqual(generated["hardBlockers"], scoring["true_blockers"])
        self.assertEqual(
            generated["thresholds"],
            {
                "applyNow": scoring["recommendation_thresholds"]["apply_now_min_fit"],
                "consider": scoring["recommendation_thresholds"]["consider_min_fit"],
                "stretch": scoring["recommendation_thresholds"]["stretch_min_fit"],
            },
        )
        self.assertEqual(generated["watchlist"]["total"], len(watchlist["companies"]))
        self.assertEqual(
            generated["watchlist"]["enabled"],
            sum(bool(company["enabled"]) for company in watchlist["companies"]),
        )

    def test_profile_is_read_only_and_contains_real_authorization_not_mock_identity(self) -> None:
        profile = (
            REPO_ROOT / "web" / "app" / "profile" / "profile-client.tsx"
        ).read_text(encoding="utf-8")
        generated = (
            REPO_ROOT / "web" / "generated" / "profile-config.json"
        ).read_text(encoding="utf-8")

        self.assertIn("read-only — edit via config", profile)
        self.assertIn("German citizenship", generated)
        self.assertIn("Skilled Worker sponsorship", generated)
        self.assertIn("COMPASS", generated)
        self.assertNotIn("US citizen", profile + generated)
        self.assertNotRegex(profile, r"(?:insert|update|delete|upsert)\(")


if __name__ == "__main__":
    unittest.main()
