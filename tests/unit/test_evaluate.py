from __future__ import annotations

from dataclasses import replace
import json
import unittest

from app.config import load_candidate_profile, load_location_policy, load_scoring_policy
from app.models import CompanyConfig, HardBlocker
from app.services.evaluate import (
    evaluate_role,
    _feasibility,
    _recommendation,
    _role_family_fit,
    _scope_seniority,
    _technical_blockers,
    _weighted_fit_score,
    relevance_decision,
)


# These band-edge tests use zip(..., strict=True), so they require Python >= 3.10.
FIT_EDGES = (49, 50, 64, 65, 79, 80)
CORE_COLD = ("skip", "stretch", "stretch", "consider", "consider", "apply_now")
CORE_WARM = ("skip", "stretch", "stretch", "consider", "apply_now", "apply_now")
TIER3_CORE = ("skip", "skip", "skip", "consider", "consider", "consider")
STRETCH_COLD = ("skip", "stretch", "stretch", "consider", "consider", "consider")
STRETCH_WARM = ("skip", "stretch", "stretch", "consider", "apply_now", "apply_now")
BLOCKED = ("blocked", "blocked", "blocked", "blocked", "blocked", "blocked")


class EvaluateDecisionLogicTest(unittest.TestCase):
    def test_core_recommendation_band_edges(self) -> None:
        scenarios = (
            ("tier1_cold_viable", 1, False, "viable", CORE_COLD),
            ("tier1_warm_viable", 1, True, "viable", CORE_WARM),
            ("tier3_cold_viable", 3, False, "viable", TIER3_CORE),
            ("tier1_cold_us_friction", 1, False, "sponsorship_required", CORE_COLD),
            ("tier1_cold_blocked", 1, False, "blocked", BLOCKED),
        )

        for name, tier, warm_path, feasibility, expected_values in scenarios:
            company = _company(tier=tier, warm_path=warm_path)
            for fit_score, expected in zip(FIT_EDGES, expected_values, strict=True):
                with self.subTest(name=name, fit_score=fit_score):
                    self.assertEqual(
                        _recommendation(fit_score, feasibility, company, []),
                        expected,
                    )

    def test_stretch_recommendation_needs_warm_path_or_upside_to_apply_now(
        self,
    ) -> None:
        scenarios = (
            ("tier1_cold", 1, False, STRETCH_COLD),
            ("tier1_warm", 1, True, STRETCH_WARM),
            ("tier2_warm", 2, True, STRETCH_COLD),
        )

        for name, tier, warm_path, expected_values in scenarios:
            company = _company(tier=tier, warm_path=warm_path)
            for fit_score, expected in zip(FIT_EDGES, expected_values, strict=True):
                with self.subTest(name=name, fit_score=fit_score):
                    self.assertEqual(
                        _recommendation(
                            fit_score,
                            "viable",
                            company,
                            [],
                            stretch_family=True,
                        ),
                        expected,
                    )

        self.assertEqual(
            _recommendation(
                80,
                "viable",
                _company(tier=1, warm_path=False),
                [],
                stretch_family=True,
                exceptional_upside=True,
            ),
            "apply_now",
        )

    def test_hard_blockers_override_recommendation(self) -> None:
        company = _company(tier=1, warm_path=True)
        blocker = HardBlocker(type="technical_role", evidence="Engineering is central.")

        self.assertEqual(_recommendation(80, "viable", company, [blocker]), "blocked")

    def test_engineering_blocker_triggers_but_strategy_titles_are_allowed(self) -> None:
        blocked_titles = (
            "Software Engineer",
            "Staff Engineer",
            "Forward Deployed Engineer",
            "Full Stack Developer",
            "Backend Platform Engineer",
            "Machine Learning Engineer",
        )
        allowed_titles = (
            "Deployment Strategist",
            "Forward-Deployed Strategist",
            "Engineering Strategist",
            "Strategy & Operations Manager",
        )

        for title in blocked_titles:
            with self.subTest(title=title):
                self.assertTrue(_technical_blockers(title.lower()))

        for title in allowed_titles:
            with self.subTest(title=title):
                self.assertFalse(_technical_blockers(title.lower()))

    def test_feasibility_by_market(self) -> None:
        cases = (
            (["Sydney, Australia"], "viable"),
            (["London, United Kingdom"], "viable"),
            (["Singapore"], "viable"),
            (["Munich, Germany"], "viable"),
            (["San Francisco, California, United States"], "sponsorship_required"),
            (["Toronto, Canada"], "uncertain"),
        )

        for locations, expected in cases:
            with self.subTest(locations=locations):
                self.assertEqual(_feasibility(locations)[0], expected)

    def test_location_policy_reason_is_config_driven(self) -> None:
        policy = load_location_policy()
        changed_australia = replace(
            policy.markets["Australia"],
            notes="Custom Australia policy note.",
            expected_availability_date="arrival_plus_6_months",
        )
        changed_policy = replace(
            policy,
            markets={**policy.markets, "Australia": changed_australia},
        )

        state, reason = _feasibility(["Sydney, Australia"], changed_policy)

        self.assertEqual(state, "viable")
        self.assertIn("Custom Australia policy note.", reason)
        self.assertIn("arrival_plus_6_months", reason)

    def test_feasibility_outcome_uses_policy_fields_not_market_name(self) -> None:
        policy = load_location_policy()
        us_as_viable = replace(
            policy.markets["United States"],
            current_authorization="viable_with_sponsorship",
            sponsorship_required=True,
            notes="US edited to viable for this test.",
        )
        singapore_as_friction = replace(
            policy.markets["Singapore"],
            current_authorization="not_authorized_high_friction",
            sponsorship_required=True,
            notes="Singapore edited to friction for this test.",
        )
        changed_policy = replace(
            policy,
            markets={
                **policy.markets,
                "United States": us_as_viable,
                "Singapore": singapore_as_friction,
            },
        )

        self.assertEqual(
            _feasibility(["San Francisco, California, United States"], changed_policy)[0],
            "viable",
        )
        self.assertEqual(
            _feasibility(["Singapore"], changed_policy)[0],
            "sponsorship_required",
        )

    def test_scoring_policy_weights_drive_fit_score(self) -> None:
        policy = load_scoring_policy()
        dimensions = {
            "role_family_fit": 100,
            "evidence_strength": 50,
            "scope_seniority": 50,
            "gap_manageability": 50,
        }
        family_only_policy = replace(
            policy,
            fit_weights={
                "role_family_fit": 1.0,
                "evidence_strength": 0.0,
                "scope_seniority": 0.0,
                "gap_manageability": 0.0,
            },
        )

        self.assertEqual(_weighted_fit_score(dimensions, family_only_policy), 100)
        self.assertLess(_weighted_fit_score(dimensions, policy), 100)

    def test_recommendation_bands_are_config_driven(self) -> None:
        policy = load_scoring_policy()
        higher_apply_thresholds = replace(
            policy.recommendation_thresholds,
            apply_now_min_fit=90,
        )
        stricter_policy = replace(
            policy,
            recommendation_thresholds=higher_apply_thresholds,
        )
        company = _company(tier=1)

        self.assertEqual(_recommendation(80, "viable", company, []), "apply_now")
        self.assertEqual(
            _recommendation(80, "viable", company, [], scoring_policy=stricter_policy),
            "consider",
        )

    def test_candidate_profile_family_patterns_drive_role_fit(self) -> None:
        profile = load_candidate_profile()
        narrowed_profile = replace(
            profile,
            primary_role_family_patterns=(r"\bchief astronaut\b",),
            stretch_role_family_patterns=(),
        )

        self.assertEqual(
            _role_family_fit(
                "Strategic Operations Manager",
                "Business Operations",
                "lead strategic operations programs",
                profile,
            ),
            92,
        )
        self.assertEqual(
            _role_family_fit(
                "Strategic Operations Manager",
                "Business Operations",
                "lead strategic operations programs",
                narrowed_profile,
            ),
            58,
        )

    def test_profile_language_match_raises_score_and_alignment_strength(self) -> None:
        company = _company(target_locations=["Munich / Germany"])
        base_row = _row(
            "Strategic Operations Manager",
            ["Munich, Germany"],
            department="Strategy & Operations",
            description="lead strategy operations programs for customers",
        )
        german_row = _row(
            "Strategic Operations Manager",
            ["Munich, Germany"],
            department="Strategy & Operations",
            description="lead strategy operations programs for customers; fluent in German required",
        )

        base = evaluate_role(base_row, company)
        german = evaluate_role(german_row, company)

        self.assertGreater(
            german.dimensions["evidence_strength"],
            base.dimensions["evidence_strength"],
        )
        self.assertGreater(german.role_fit_score, base.role_fit_score)
        self.assertIn(
            "German is listed in the profile as native.",
            [alignment.candidate_evidence for alignment in german.alignments],
        )

    def test_english_and_bare_language_mentions_do_not_raise_score(self) -> None:
        company = _company(target_locations=["Munich / Germany"])
        base_row = _row(
            "Strategic Operations Manager",
            ["Munich, Germany"],
            department="Strategy & Operations",
            description="lead strategy operations programs for customers",
        )
        english_row = _row(
            "Strategic Operations Manager",
            ["Munich, Germany"],
            department="Strategy & Operations",
            description="lead strategy operations programs for English-speaking customers",
        )
        bare_german_row = _row(
            "Strategic Operations Manager",
            ["Munich, Germany"],
            department="Strategy & Operations",
            description="lead strategy operations programs for customers in the German market",
        )

        base = evaluate_role(base_row, company)
        english = evaluate_role(english_row, company)
        bare_german = evaluate_role(bare_german_row, company)

        self.assertEqual(
            english.dimensions["evidence_strength"],
            base.dimensions["evidence_strength"],
        )
        self.assertEqual(
            bare_german.dimensions["evidence_strength"],
            base.dimensions["evidence_strength"],
        )
        self.assertNotIn(
            "German is listed in the profile as native.",
            [alignment.candidate_evidence for alignment in bare_german.alignments],
        )

    def test_associate_strategy_role_is_not_auto_scored_low(self) -> None:
        self.assertEqual(_scope_seniority("Strategy Intern", "strategic operations"), 35)
        self.assertGreater(
            _scope_seniority("Associate Strategy Analyst", "strategy operations"),
            35,
        )
        self.assertGreaterEqual(
            _scope_seniority(
                "Strategy and Operations Associate",
                "own cross-functional strategic program and drive executive rhythm",
            ),
            70,
        )

    def test_core_families_score_above_stretch_families(self) -> None:
        core = _role_family_fit(
            "Strategic Operations Manager",
            "Business Operations",
            "lead strategic operations and business transformation programs",
        )
        stretch = _role_family_fit(
            "Deployment Strategist",
            "Professional Services Operations",
            "deployment strategist role with program leadership and customer deployment",
        )

        self.assertGreater(core, stretch)

    def test_relevance_filter_covers_primary_and_stretch_families(self) -> None:
        company = _company(target_locations=["London / UK", "Sydney / Australia", "Singapore"])
        accepted_titles = (
            "S&O Lead",
            "Strategic Operations Lead",
            "Business Operations Manager",
            "Business Ops Manager",
            "Product Operations Lead",
            "Product Ops Lead",
            "Product Strategy Manager",
            "Revenue Operations Manager",
            "Revenue Ops Manager",
            "GTM Strategy and Operations Lead",
            "Sales S&O Lead",
            "Go-to-Market Program Lead",
            "Business Transformation Manager",
            "Strategic Programs Lead",
            "Chief of Staff",
            "BizOps Lead",
            "Deployment Strategist",
            "Forward-Deployed Strategist",
        )

        for title in accepted_titles:
            with self.subTest(title=title):
                decision = relevance_decision(_row(title, ["London, United Kingdom"]), company)
                self.assertTrue(decision.should_evaluate)
                self.assertEqual(decision.reason, "matched_target_location_and_role_family")

    def test_relevance_filter_records_skip_reasons(self) -> None:
        company = _company(target_locations=["London / UK"])

        self.assertEqual(
            relevance_decision(
                _row("Strategic Operations Lead", ["New York, United States"]),
                company,
            ).reason,
            "non_target_location",
        )
        self.assertEqual(
            relevance_decision(
                _row("Account Executive", ["London, United Kingdom"]),
                company,
            ).reason,
            "no_primary_or_stretch_family_signal",
        )


def _company(
    *,
    tier: int = 1,
    warm_path: bool = False,
    target_locations: list[str] | None = None,
) -> CompanyConfig:
    return CompanyConfig(
        name="ExampleCo",
        tier=tier,
        enabled=True,
        ats_type="greenhouse",
        source_key="example",
        careers_url="https://example.com/careers",
        target_locations=target_locations or ["London / UK"],
        target_role_family_notes="Strategy and operations",
        warm_path=warm_path,
    )


def _row(
    title: str,
    locations: list[str],
    department: str = "",
    description: str = "",
) -> dict[str, str]:
    return {
        "title": title,
        "locations_json": json.dumps(locations),
        "department": department,
        "description_text": description or title,
    }


if __name__ == "__main__":
    unittest.main()
