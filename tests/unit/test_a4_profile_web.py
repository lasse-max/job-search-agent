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
        self.assertEqual(generated["toolsAndSkills"], candidate["tools_and_skills"])
        self.assertEqual(
            generated["locations"]["allowedMetros"],
            locations["profile_display"]["allowed_metros"],
        )
        self.assertEqual(len(generated["locations"]["allowedMetros"]), 14)
        self.assertIn("Perth", generated["locations"]["allowedMetros"])
        self.assertIn("Brisbane", generated["locations"]["allowedMetros"])
        self.assertNotIn("Madrid", generated["locations"]["allowedMetros"])
        self.assertIn(
            "\\b(?:sydney|melbourne|perth|brisbane)\\b",
            locations["pre_evaluation_filter"]["allowed_location_patterns"],
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
        generated_companies = {
            company["name"]: company for company in generated["watchlist"]["companies"]
        }
        for company in watchlist["companies"]:
            generated_company = generated_companies[company["name"]]
            self.assertEqual(generated_company["tier"], company["tier"])
            self.assertEqual(generated_company["enabled"], bool(company["enabled"]))
            self.assertEqual(generated_company["atsType"], company.get("ats_type", "unknown"))
            self.assertEqual(generated_company["sourceKey"], company.get("source_key"))
            self.assertEqual(
                generated_company["supportedAdapter"], company.get("supported_adapter")
            )
            self.assertEqual(
                generated_company["jobCountAtAudit"], company.get("job_count_at_audit")
            )
            self.assertEqual(generated_company["careersUrl"], company.get("careers_url"))
            self.assertEqual(
                generated_company["sourceEvidenceUrl"],
                company.get("source_evidence_url"),
            )
            self.assertEqual(
                generated_company["manualFallback"], company.get("manual_fallback")
            )
            self.assertEqual(generated_company["notes"], company.get("notes"))
            self.assertEqual(
                generated_company["darkReasonCode"],
                _expected_dark_reason(company),
            )

        expected_coverage = _expected_coverage(watchlist["companies"])
        expected_coverage["byTier"] = [
            {"tier": tier, **_expected_coverage(
                [company for company in watchlist["companies"] if company["tier"] == tier]
            )}
            for tier in (1, 2, 3)
        ]
        expected_coverage["darkByReason"] = {
            reason: sum(
                _expected_dark_reason(company) == reason
                for company in watchlist["companies"]
            )
            for reason in (
                "missing_source",
                "adapter_ready_disabled",
                "dead_feed",
                "manual_only",
            )
        }
        self.assertEqual(generated["watchlist"]["coverage"], expected_coverage)
        self.assertEqual(generated_companies["Google"]["darkReasonCode"], "manual_only")
        self.assertEqual(generated_companies["Atlassian"]["darkReasonCode"], "dead_feed")
        self.assertEqual(
            generated_companies["Cohere"]["darkReasonCode"],
            "adapter_ready_disabled",
        )
        self.assertIsNone(generated_companies["Databricks"]["darkReasonCode"])

    def test_profile_is_read_only_and_contains_real_authorization_not_mock_identity(self) -> None:
        profile = (
            REPO_ROOT / "web" / "app" / "profile" / "profile-client.tsx"
        ).read_text(encoding="utf-8")
        generated = (
            REPO_ROOT / "web" / "generated" / "profile-config.json"
        ).read_text(encoding="utf-8")

        self.assertIn("read-only — edit via config", profile)
        self.assertIn("Tools + skills", profile)
        self.assertIn("German citizenship", generated)
        self.assertIn("Skilled Worker sponsorship", generated)
        self.assertIn("COMPASS", generated)
        self.assertNotIn("US citizen", profile + generated)
        self.assertNotRegex(profile, r"(?:insert|update|delete|upsert)\(")

    def test_watchlist_coverage_is_actionable_and_reconciles_to_config(self) -> None:
        profile = (
            REPO_ROOT / "web" / "app" / "profile" / "profile-client.tsx"
        ).read_text(encoding="utf-8")
        data_layer = (
            REPO_ROOT / "web" / "lib" / "data" / "profile.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("Watchlist coverage · B-27", profile)
        self.assertIn("Coverage", profile)
        self.assertIn("All companies by tier · scan status", profile)
        self.assertIn("Tier {tier} · {scannedCount}/{tierCompanies.length} scanned", profile)
        self.assertIn("data.live.companyStatuses[company.name]?.status", profile)
        self.assertIn("dead feed ·", profile)
        self.assertIn("ats_type: unknown · source_key: null", profile)
        self.assertIn("adapter_ready_disabled", profile)
        self.assertIn('tone === "red"', profile)
        self.assertIn('tone === "amber"', profile)
        self.assertIn("text-chart-warn", profile)
        self.assertIn("Scanned ${data.live.fetchedPostings.toLocaleString", profile)
        self.assertIn('supabase.from("job_sources").select("*")', data_layer)
        self.assertIn("configuredEnabledNames", data_layer)
        self.assertIn("missingConfiguredCompanies", data_layer)
        self.assertIn("extraDatabaseEnabledCompanies", data_layer)
        self.assertIn("enabledCountMismatch", data_layer)
        self.assertIn("companyStatuses", data_layer)
        self.assertIn("worstRunStatus", data_layer)


def _expected_dark_reason(company: dict[str, object]) -> str | None:
    if company["enabled"]:
        return None
    if company.get("job_count_at_audit") == 0:
        return "dead_feed"
    if not company.get("ats_type") or company.get("ats_type") == "unknown":
        return "missing_source"
    if (
        company.get("supported_adapter")
        in {"ashby", "greenhouse", "lever", "smartrecruiters"}
        and company.get("ats_type")
        in {"ashby", "greenhouse", "lever", "smartrecruiters"}
    ):
        return "adapter_ready_disabled"
    return "manual_only"


def _expected_coverage(companies: list[dict[str, object]]) -> dict[str, object]:
    scanned = sum(bool(company["enabled"]) for company in companies)
    total = len(companies)
    percentage = int((scanned / total * 100) + 0.5) if total else 0
    tone = "red" if percentage < 50 else "amber" if percentage <= 80 else "green"
    return {
        "scanned": scanned,
        "total": total,
        "percentage": percentage,
        "tone": tone,
        "dark": total - scanned,
    }


if __name__ == "__main__":
    unittest.main()
