from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
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
    _is_stretch_family,
    has_disqualifying_hard_requirement,
    relevance_decision,
)


# These band-edge tests use zip(..., strict=True), so they require Python >= 3.10.
FIT_EDGES = (59, 60, 69, 70, 79, 80)
STRICT_BANDS = ("skip", "stretch", "stretch", "consider", "consider", "apply_now")
BLOCKED = ("blocked", "blocked", "blocked", "blocked", "blocked", "blocked")


class EvaluateDecisionLogicTest(unittest.TestCase):
    def test_core_recommendation_band_edges(self) -> None:
        scenarios = (
            ("tier1_cold_viable", 1, False, "viable", STRICT_BANDS),
            ("tier1_warm_viable", 1, True, "viable", STRICT_BANDS),
            ("tier3_cold_viable", 3, False, "viable", STRICT_BANDS),
            ("tier1_cold_us_friction", 1, False, "sponsorship_required", STRICT_BANDS),
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

    def test_stretch_recommendation_uses_same_monotonic_fit_bands(
        self,
    ) -> None:
        scenarios = (
            ("tier1_cold", 1, False, STRICT_BANDS),
            ("tier1_warm", 1, True, STRICT_BANDS),
            ("tier2_warm", 2, True, STRICT_BANDS),
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
                79,
                "viable",
                _company(tier=1, warm_path=False),
                [],
                stretch_family=True,
                exceptional_upside=True,
            ),
            "consider",
        )

    def test_hard_blockers_override_recommendation(self) -> None:
        company = _company(tier=1, warm_path=True)
        blocker = HardBlocker(type="technical_role", evidence="Engineering is central.")

        self.assertEqual(_recommendation(80, "viable", company, [blocker]), "blocked")

    def test_us_without_warm_path_blocks_but_warm_path_softens(self) -> None:
        row = _row(
            "Principal Strategy and Operations",
            ["San Mateo (US)"],
            department="Strategy & Operations",
            description="lead strategy operations programs",
        )

        cold = evaluate_role(row, _company(tier=2, warm_path=False))
        warm = evaluate_role(row, _company(tier=3, warm_path=True))

        self.assertEqual(cold.recommendation, "blocked")
        self.assertEqual(cold.feasibility["state"], "blocked")
        self.assertIn(
            "location_work_authorization",
            [blocker.type for blocker in cold.hard_blockers],
        )
        self.assertEqual(warm.feasibility["state"], "sponsorship_required")
        self.assertEqual(warm.recommendation, "consider")

    def test_security_clearance_and_technical_pm_depth_block(self) -> None:
        clearance = evaluate_role(
            _row(
                "Deployment Strategist",
                ["London, United Kingdom"],
                department="Professional Services Operations",
                description="requires SC clearance and continuous UK residency",
            ),
            _company(tier=2),
        )
        technical_pm = evaluate_role(
            _row(
                "Product Manager, Payments",
                ["London, United Kingdom"],
                department="Product",
                description=(
                    "requires product management experience, technical specifications, "
                    "experimentation, and engineering to design scalable solutions"
                ),
            ),
            _company(tier=2),
        )

        self.assertEqual(clearance.recommendation, "blocked")
        self.assertIn(
            "security_clearance",
            [blocker.type for blocker in clearance.hard_blockers],
        )
        no_clearance = evaluate_role(
            _row(
                "Deployment Strategist",
                ["London, United Kingdom"],
                department="Professional Services Operations",
                description="lead customer deployment strategy and operational planning",
            ),
            _company(name="Arondite", tier=3),
        )
        self.assertNotIn(
            "security_clearance",
            [blocker.type for blocker in no_clearance.hard_blockers],
        )
        self.assertEqual(technical_pm.recommendation, "blocked")
        self.assertIn(
            "technical_pm_depth",
            [blocker.type for blocker in technical_pm.hard_blockers],
        )

    def test_required_technical_hard_requirements_block_but_preferred_do_not(
        self,
    ) -> None:
        required = evaluate_role(
            _row(
                "Strategic Operations Lead",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description=(
                    "Minimum qualifications: Bachelor's degree in Computer Science "
                    "required. Lead strategic operations programs."
                ),
            ),
            _company(tier=1),
        )
        preferred = evaluate_role(
            _row(
                "Strategic Operations Lead",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description=(
                    "Preferred: familiarity with Python and exposure to software "
                    "development. Lead strategic operations programs."
                ),
            ),
            _company(tier=1),
        )
        broad_degree = evaluate_role(
            _row(
                "Strategic Operations Lead",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description=(
                    "Minimum qualifications: Bachelor's degree in Business, "
                    "Economics, Engineering, or a related field. Lead strategic "
                    "operations programs."
                ),
            ),
            _company(tier=1),
        )
        technical_deployment = evaluate_role(
            _row(
                "AI Deployment Strategist - Paris",
                ["Paris, France"],
                department="Solutions",
                description=(
                    "About you. You hold a degree in Computer Science or Engineering. "
                    "Hands-on experience building and deploying AI applications in "
                    "Python is required. Lead executive discovery and business value work."
                ),
            ),
            _company(tier=1, target_locations=["Paris / France"]),
        )

        self.assertEqual(required.recommendation, "blocked")
        self.assertIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in required.hard_blockers],
        )
        self.assertEqual(technical_deployment.recommendation, "blocked")
        self.assertIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in technical_deployment.hard_blockers],
        )
        self.assertNotIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in preferred.hard_blockers],
        )

        for description in (
            (
                "At Acme, we build production software for enterprises. You will "
                "lead customer strategy and operations."
            ),
            (
                "You will collaborate with engineers who build production software. "
                "You lead strategic discovery."
            ),
            (
                "Our engineering team is proficient in Python and builds the platform. "
                "This role leads customer strategy."
            ),
            (
                "The platform uses advanced Python programming. You lead implementation "
                "strategy."
            ),
            (
                "This role leads customer strategy while the platform uses advanced "
                "Python programming."
            ),
        ):
            with self.subTest(business_first=description):
                business_first = evaluate_role(
                    _row(
                        "AI Deployment Strategist",
                        ["London, United Kingdom"],
                        department="Professional Services",
                        description=description,
                    ),
                    _company(tier=1),
                )
                self.assertNotIn(
                    "disqualifying_hard_requirement",
                    [blocker.type for blocker in business_first.hard_blockers],
                )

        for description in (
            "Production coding, Python, and machine learning experience preferred.",
            (
                "Hands-on building AI applications, Python, and ML experience are "
                "preferred."
            ),
        ):
            with self.subTest(trailing_preference=description):
                trailing_preference = evaluate_role(
                    _row(
                        "AI Deployment Strategist",
                        ["London, United Kingdom"],
                        department="Professional Services",
                        description=(
                            f"{description} Lead customer deployment strategy and "
                            "operational planning."
                        ),
                    ),
                    _company(tier=1),
                )
                self.assertNotIn(
                    "disqualifying_hard_requirement",
                    [blocker.type for blocker in trailing_preference.hard_blockers],
                )
        self.assertNotIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in broad_degree.hard_blockers],
        )

    def test_required_credentials_downrank_without_hard_blocking(self) -> None:
        base = evaluate_role(
            _row(
                "Strategic Operations Lead",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description="Lead strategic operations programs and executive reporting.",
            ),
            _company(tier=1),
        )
        credentialed = evaluate_role(
            _row(
                "Strategic Operations Lead",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description=(
                    "Requirements: PMP certification and intermediate platform "
                    "certification within six months. Lead strategic operations "
                    "programs and executive reporting."
                ),
            ),
            _company(tier=1),
        )

        self.assertGreater(base.role_fit_score, credentialed.role_fit_score)
        self.assertGreater(
            base.dimensions["gap_manageability"],
            credentialed.dimensions["gap_manageability"],
        )
        self.assertNotIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in credentialed.hard_blockers],
        )

    def test_technical_depth_hard_requirements_block_with_common_phrasings(
        self,
    ) -> None:
        cases = (
            "This role requires production software development in customer environments.",
            "Mandatory advanced Python programming for deployment architecture.",
            "You must own deep ML engineering work for customer deployments.",
            "You need to write production code for deployed customer systems.",
            "You are proficient in Python and own deployment architecture.",
        )

        for description in cases:
            with self.subTest(description=description):
                evaluation = evaluate_role(
                    _row(
                        "AI Deployment Strategist",
                        ["London, United Kingdom"],
                        department="Professional Services",
                        description=(
                            f"{description} Lead customer deployment strategy and "
                            "operational planning."
                        ),
                    ),
                    _company(tier=1),
                )

                self.assertEqual(evaluation.recommendation, "blocked")
                self.assertIn(
                    "disqualifying_hard_requirement",
                    [blocker.type for blocker in evaluation.hard_blockers],
                )

        preferred = evaluate_role(
            _row(
                "AI Deployment Strategist",
                ["London, United Kingdom"],
                department="Professional Services",
                description=(
                    "Preferred: strong Python programming and production coding "
                    "experience. Lead customer deployment strategy and operational "
                    "planning."
                ),
            ),
            _company(tier=1),
        )

        self.assertNotIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in preferred.hard_blockers],
        )

    def test_preferred_neighbor_does_not_cancel_required_technical_clause(
        self,
    ) -> None:
        cases = (
            "A computer science degree is required, while Python is preferred.",
            "Must have production coding, with ML familiarity preferred.",
            "A computer science degree is required and Python is preferred.",
            "Production coding is required but ML familiarity is preferred.",
            "Python is preferred but production coding is required.",
            "Python preferred and a computer science degree is required.",
            (
                "A bachelor's degree in Computer Science and Engineering is required, "
                "Python preferred."
            ),
        )

        for description in cases:
            with self.subTest(description=description):
                evaluation = evaluate_role(
                    _row(
                        "AI Deployment Strategist",
                        ["London, United Kingdom"],
                        department="Professional Services",
                        description=(
                            f"{description} Lead customer deployment strategy and "
                            "operational planning."
                        ),
                    ),
                    _company(tier=1),
                )

                self.assertEqual(evaluation.recommendation, "blocked")
                self.assertIn(
                    "disqualifying_hard_requirement",
                    [blocker.type for blocker in evaluation.hard_blockers],
                )

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
            (["Perth"], "viable"),
            (["London, United Kingdom"], "viable"),
            (["Singapore"], "viable"),
            (["Munich, Germany"], "viable"),
            (["San Francisco, California, United States"], "sponsorship_required"),
            (["San Mateo (US)"], "sponsorship_required"),
            (["Glendale (US)"], "sponsorship_required"),
            (["Glendale, Scotland"], "uncertain"),
            (["Toronto, Canada"], "uncertain"),
        )

        for locations, expected in cases:
            with self.subTest(locations=locations):
                self.assertEqual(_feasibility(locations)[0], expected)

        perth = relevance_decision(
            _row(
                "Strategic Operations Manager",
                ["Perth"],
                department="Strategy & Operations",
            ),
            _company(target_locations=["Perth / Australia"]),
        )
        self.assertTrue(perth.should_evaluate)

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
                "Partner Operations Lead",
                "Channel Operations",
                "own partner field operations and channel planning",
                profile,
            ),
            92,
        )
        self.assertEqual(
            _role_family_fit(
                "Partnerships Sales Manager",
                "Business Development",
                "carry quota and close partner sales deals",
                profile,
            ),
            58,
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
        self.assertEqual(
            _role_family_fit(
                "Product Monetisation & Pricing Lead",
                "Product",
                "own product packaging, pricing strategy, and monetisation roadmap",
                profile,
            ),
            92,
        )

    def test_program_management_is_stretch_only_for_business_scope(self) -> None:
        self.assertTrue(
            _is_stretch_family(
                "Technical Program Manager",
                "Transformation",
                "Own a cross-functional business transformation and change-management program.",
            )
        )
        self.assertFalse(
            _is_stretch_family(
                "Technical Program Manager",
                "Engineering",
                "Own SDLC release trains, software delivery, and infrastructure dependencies.",
            )
        )
        business = relevance_decision(
            _row(
                "Technical Program Manager",
                ["London, United Kingdom"],
                department="Transformation",
                description="Own business transformation and cross-functional change management.",
            ),
            _company(tier=2),
        )
        engineering = relevance_decision(
            _row(
                "Technical Program Manager",
                ["London, United Kingdom"],
                department="Engineering",
                description="Own SDLC releases and pure software engineering delivery.",
            ),
            _company(tier=2),
        )

        self.assertTrue(business.should_evaluate)
        self.assertFalse(engineering.should_evaluate)
        self.assertEqual(engineering.reason, "excluded_title_department_function")

    def test_required_technical_degree_is_scoped_to_its_clause(self) -> None:
        self.assertTrue(
            has_disqualifying_hard_requirement(
                "What we're looking for Required Engineering or computer science degree "
                "from a top tier institution. Translate business problems into models."
            )
        )
        self.assertFalse(
            has_disqualifying_hard_requirement(
                "A degree in business, economics, or engineering is required."
            )
        )

    def test_native_product_director_is_downranked_without_strategy_ops_scope(self) -> None:
        evaluation = evaluate_role(
            _row(
                "Product Director, Financial Markets & Financial Platform",
                ["Singapore"],
                department="Product",
                description=(
                    "Own the product roadmap, manage product managers, and partner with "
                    "engineering to launch financial-platform features."
                ),
            ),
            _company(tier=1, target_locations=["Singapore"]),
        )

        self.assertLess(evaluation.role_fit_score, 60)
        self.assertEqual(evaluation.recommendation, "skip")

    def test_stage19_location_allowlist_adds_brisbane_and_drops_spain(self) -> None:
        brisbane = relevance_decision(
            _row(
                "Strategy and Operations Manager",
                ["Brisbane, Australia"],
                department="Business Operations",
                description="Own strategic planning and operating cadence.",
            ),
            _company(tier=2),
        )
        madrid = relevance_decision(
            _row(
                "Strategy and Operations Manager",
                ["Madrid, Spain"],
                department="Business Operations",
                description="Own strategic planning and operating cadence.",
            ),
            _company(tier=2),
        )

        self.assertTrue(brisbane.should_evaluate)
        self.assertFalse(madrid.should_evaluate)
        self.assertEqual(madrid.reason, "location_filter_not_allowed")

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

    def test_unsupported_required_language_skips_and_profile_languages_do_not(
        self,
    ) -> None:
        company = _company(target_locations=["Paris / France"])
        french = evaluate_role(
            _row(
                "Strategist, Agent Development (French speaking)",
                ["Paris, France"],
                department="Product",
                description="Lead agent strategy for customers.",
            ),
            company,
        )
        german = evaluate_role(
            _row(
                "Strategic Operations Manager (German speaking)",
                ["Munich, Germany"],
                department="Strategy & Operations",
                description="Lead strategic operations programs.",
            ),
            _company(target_locations=["Munich / Germany"]),
        )
        english = evaluate_role(
            _row(
                "Strategic Operations Manager",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description="Fluent English required. Lead strategic operations programs.",
            ),
            _company(target_locations=["London / UK"]),
        )

        mandarin = relevance_decision(
            _row(
                "Manager, Revenue Strategy",
                ["Singapore"],
                department="Revenue Strategy",
                description="Fluency in Mandarin is required for customer work.",
            ),
            _company(target_locations=["Singapore"]),
        )
        cantonese = evaluate_role(
            _row(
                "Strategist, Agent Development (Cantonese Speaking)",
                ["Singapore"],
                department="Product",
                description=(
                    "Lead agent strategy for customers. English is preferred for "
                    "cross-region work."
                ),
            ),
            _company(target_locations=["Singapore"]),
        )
        generic_title_language = relevance_decision(
            _row(
                "Strategic Operations Manager (Thai Speaking)",
                ["Singapore"],
                department="Strategy & Operations",
                description="Lead regional strategy and operations programs.",
            ),
            _company(target_locations=["Singapore"]),
        )
        preferred_french = relevance_decision(
            _row(
                "Strategic Operations Manager",
                ["Paris, France"],
                department="Strategy & Operations",
                description=(
                    "French-speaking capability is preferred, not required. Lead "
                    "regional strategy and operations programs."
                ),
            ),
            _company(target_locations=["Paris / France"]),
        )

        self.assertEqual(
            relevance_decision(
                _row(
                    "Strategist, Agent Development (Spanish speaking)",
                    ["Paris, France"],
                    department="Product",
                    description="Lead agent strategy for customers.",
                ),
                _company(target_locations=["Paris / France"]),
            ).reason,
            "unsupported_language_requirement",
        )
        self.assertEqual(french.recommendation, "skip")
        self.assertLess(french.role_fit_score, 60)
        self.assertEqual(mandarin.reason, "unsupported_language_requirement")
        self.assertEqual(cantonese.recommendation, "skip")
        self.assertLess(cantonese.role_fit_score, 60)
        self.assertEqual(
            generic_title_language.reason,
            "unsupported_language_requirement",
        )
        self.assertNotEqual(german.recommendation, "skip")
        self.assertNotEqual(english.recommendation, "skip")
        self.assertNotEqual(
            preferred_french.reason,
            "unsupported_language_requirement",
        )

    def test_generic_speaking_marker_does_not_invent_a_language(self) -> None:
        decision = relevance_decision(
            _row(
                "Customer Operations Manager",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description=(
                    "Lead a customer-facing and English-speaking team across "
                    "strategic operating programs."
                ),
            ),
            _company(target_locations=["London / UK"]),
        )

        self.assertNotEqual(decision.reason, "unsupported_language_requirement")

    def test_supported_or_language_alternative_passes_but_and_requirement_blocks(
        self,
    ) -> None:
        company = _company(target_locations=["London / UK"])
        for description in (
            "Fluency in German or French required for partner work.",
            "German or French fluency is required for partner work.",
            "English, German, or French fluency is required for partner work.",
            "Fluency in English, German, or French is required for partner work.",
            "English, French, or Spanish fluency is required for partner work.",
            "Fluency in English, French, or Spanish is required for partner work.",
            "German, Mandarin, or Cantonese is required for partner work.",
        ):
            with self.subTest(description=description):
                decision = relevance_decision(
                    _row(
                        "Strategic Operations Manager",
                        ["London, United Kingdom"],
                        department="Strategy & Operations",
                        description=description,
                    ),
                    company,
                )
                self.assertNotEqual(
                    decision.reason,
                    "unsupported_language_requirement",
                )

        mandatory = relevance_decision(
            _row(
                "Strategic Operations Manager",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description="English, German, and Mandarin are required for partner work.",
            ),
            company,
        )
        self.assertEqual(mandatory.reason, "unsupported_language_requirement")

    def test_unlisted_required_languages_are_blocked_without_blocking_sql(self) -> None:
        company = _company(target_locations=["London / UK"])
        cases = (
            (
                "Strategic Operations Manager - Russian Speaking",
                "Lead regional strategy and operations programs.",
            ),
            (
                "Strategic Operations Manager (Filipino Speaking)",
                "Lead regional strategy and operations programs.",
            ),
            (
                "Strategic Operations Manager",
                "Fluency in Hindi is required for partner work.",
            ),
            (
                "Strategic Operations Manager",
                "Fluency in Yoruba is required for partner work.",
            ),
            (
                "Strategic Operations Manager (Zulu Speaking)",
                "Lead regional strategy and operations programs.",
            ),
            (
                "Strategic Operations Manager",
                "Fluency in Somali is required for partner work.",
            ),
        )
        for title, description in cases:
            with self.subTest(title=title, description=description):
                self.assertEqual(
                    relevance_decision(
                        _row(
                            title,
                            ["London, United Kingdom"],
                            department="Strategy & Operations",
                            description=description,
                        ),
                        company,
                    ).reason,
                    "unsupported_language_requirement",
                )

        allowed_cases = (
            ("Strategic Operations Manager", "Fluency in SQL is required."),
            ("Strategic Operations Manager", "Fluency in SaaS is required."),
            ("Strategic Operations Manager", "Fluency in business is required."),
            ("Program Manager (Public Speaking)", "Lead executive communications."),
        )
        for title, description in allowed_cases:
            with self.subTest(allowed_title=title, allowed_description=description):
                decision = relevance_decision(
                    _row(
                        title,
                        ["London, United Kingdom"],
                        department="Strategy & Operations",
                        description=description,
                    ),
                    company,
                )
                self.assertNotEqual(
                    decision.reason,
                    "unsupported_language_requirement",
                )

    def test_configured_employer_opt_out_skips_without_scorer_brand_logic(self) -> None:
        row = _row(
            "Deployment Strategist - Echo",
            ["London, United Kingdom"],
            department="Professional Services",
            description="Lead commercial customer deployment strategy and operations.",
        )

        opted_out = relevance_decision(row, _company(name="Palantir", tier=1))
        control = relevance_decision(row, _company(name="OtherCo", tier=1))
        evaluation = evaluate_role(row, _company(name="Palantir", tier=1))

        self.assertEqual(opted_out.reason, "employer_opt_out")
        self.assertTrue(control.should_evaluate)
        self.assertEqual(evaluation.recommendation, "skip")
        self.assertLess(evaluation.role_fit_score, 60)
        evaluator_source = Path("app/services/evaluate.py").read_text(encoding="utf-8")
        self.assertNotIn("palantir", evaluator_source.casefold())

    def test_aggregate_careers_page_language_markers_do_not_contaminate_role(
        self,
    ) -> None:
        company = _company(target_locations=["Munich / Germany"])
        row = _row(
            "Strategist, Agent Development",
            ["Munich, Germany"],
            department="Product",
            description=(
                "Open roles Department All departments Engineering Software Engineer, "
                "Agent Product Product Manager, Agent Development Sales Sales Engineer "
                "Recruiting Recruiter Agent Strategist Strategist, Agent Development "
                "(French speaking) Strategist, Agent Development (Spanish speaking)"
            ),
        )

        decision = relevance_decision(row, company)
        evaluation = evaluate_role(row, company)

        self.assertTrue(decision.should_evaluate)
        self.assertNotEqual(decision.reason, "unsupported_language_requirement")
        self.assertNotEqual(evaluation.recommendation, "skip")

    def test_government_defense_roles_are_skipped_without_brand_logic(self) -> None:
        government = evaluate_role(
            _row(
                "Deployment Strategist - AUS Government",
                ["Sydney, Australia"],
                department="Professional Services",
                description="Lead deployment strategy for public sector customers.",
            ),
            _company(tier=1, target_locations=["Sydney / Australia"]),
        )
        control_phrase = evaluate_role(
            _row(
                "Risk Operations Manager",
                ["London, United Kingdom"],
                department="Risk Operations",
                description="Serve as a first line of defense for compliance controls.",
            ),
            _company(tier=2),
        )
        optional_defense = relevance_decision(
            _row(
                "AI Deployment Strategist, Cybersecurity - EMEA",
                ["Paris, France"],
                department="Solutions",
                description=(
                    "Lead customer deployments and executive workshops. "
                    "Prior experience with defense or sovereign cloud environments "
                    "is a plus."
                ),
            ),
            _company(tier=2, target_locations=["Paris / France"]),
        )

        self.assertEqual(government.recommendation, "skip")
        self.assertLess(government.role_fit_score, 60)
        self.assertNotIn(
            "security_clearance",
            [blocker.type for blocker in government.hard_blockers],
        )
        self.assertNotIn(
            "security_clearance",
            [blocker.type for blocker in control_phrase.hard_blockers],
        )
        self.assertTrue(optional_defense.should_evaluate)

    def test_pre_sales_value_partner_and_adjacent_ops_noise_skip(self) -> None:
        cases = (
            (
                "Principal Client Value Partner",
                "Value Engineering",
                "Own value selling, pre-sales discovery, and customer demos.",
            ),
            (
                "Logistics Standards Manager",
                "Operations",
                "Own logistics standards and operating procedures.",
            ),
            (
                "Risk and Compliance Operations Manager",
                "Operations",
                "Own risk operations and compliance workflows.",
            ),
            (
                "Integration Manager",
                "Operations",
                "Manage partner integration activities and launch checklists.",
            ),
        )

        for title, department, description in cases:
            with self.subTest(title=title):
                evaluation = evaluate_role(
                    _row(
                        title,
                        ["London, United Kingdom"],
                        department=department,
                        description=description,
                    ),
                    _company(tier=2),
                )
                self.assertEqual(evaluation.recommendation, "skip")
                self.assertLess(evaluation.role_fit_score, 60)

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

    def test_title_seniority_alone_never_skips_an_otherwise_fit_role(self) -> None:
        director = evaluate_role(
            _row(
                "Director, Strategy and Operations",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description="own cross-functional strategic programs and drive executive rhythm",
            ),
            _company(name="Spotify", tier=2),
        )
        head_of = evaluate_role(
            _row(
                "Head of Business Operations",
                ["London, United Kingdom"],
                department="Business Operations",
                description="own cross-functional strategic programs and drive executive rhythm",
            ),
            _company(name="Airbnb", tier=1),
        )
        chief_of_staff = evaluate_role(
            _row(
                "Chief of Staff",
                ["London, United Kingdom"],
                department="Strategy & Operations",
                description="own cross-functional strategic programs and drive executive rhythm",
            ),
            _company(name="Spotify", tier=2),
        )
        startup_head = evaluate_role(
            _row(
                "Head of Business Operations",
                ["London, United Kingdom"],
                department="Business Operations",
                description=(
                    "early-stage startup team of 25; own cross-functional strategic "
                    "programs and drive executive rhythm"
                ),
            ),
            _company(name="SmallStartup", tier=2),
        )

        self.assertNotEqual(director.recommendation, "skip")
        self.assertGreaterEqual(director.dimensions["scope_seniority"], 50)
        self.assertNotEqual(head_of.recommendation, "skip")
        self.assertNotEqual(chief_of_staff.recommendation, "skip")
        self.assertNotEqual(startup_head.recommendation, "skip")

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
            "Strategic Program Manager",
            "Chief of Staff",
            "BizOps Lead",
            "Deployment Strategist",
            "Forward-Deployed Strategist",
        )

        for title in accepted_titles:
            with self.subTest(title=title):
                decision = relevance_decision(_row(title, ["London, United Kingdom"]), company)
                self.assertTrue(decision.should_evaluate)
                self.assertEqual(decision.reason, "matched_title_department_role_family")

    def test_relevance_filter_records_skip_reasons(self) -> None:
        company = _company(target_locations=["London / UK"])

        self.assertEqual(
            relevance_decision(
                _row("Strategic Operations Lead", ["New York, United States"]),
                company,
            ).reason,
            "location_filter_us_requires_tier1_sponsorship_exceptional_role",
        )
        self.assertEqual(
            relevance_decision(
                _row("Account Executive", ["London, United Kingdom"]),
                company,
            ).reason,
            "excluded_title_department_function",
        )

    def test_relevance_filter_blocks_off_family_program_and_sales_titles(self) -> None:
        company = _company(target_locations=["London / UK"])
        cases = (
            "Engineering Program Manager",
            "Technical Program Manager",
            "Technical Product Manager, GTM Platform",
            "Account Executive",
            "SDR",
            "Recruiter, G&A or GTM",
            "Site Reliability Operations Analyst",
            "Solutions Architect, GTM Operations",
            "Solutions Engineer, Large Enterprise",
            "Principal Client Value Partner",
            "Lead Value Engineer",
        )

        for title in cases:
            with self.subTest(title=title):
                decision = relevance_decision(
                    _row(title, ["London, United Kingdom"], department="Operations"),
                    company,
                )
                self.assertFalse(decision.should_evaluate)
                self.assertEqual(decision.reason, "excluded_title_department_function")

    def test_location_gate_uses_posted_location_policy(self) -> None:
        tier1 = _company(tier=1)
        tier2 = _company(tier=2)

        self.assertTrue(
            relevance_decision(
                _row("Strategic Operations Lead", ["London, United Kingdom"]),
                tier2,
            ).should_evaluate
        )
        self.assertFalse(
            relevance_decision(
                _row("Strategic Operations Lead", ["Toronto, Canada"]),
                tier1,
            ).should_evaluate
        )
        self.assertEqual(
            relevance_decision(
                _row("Strategic Operations Lead", ["Dublin, Ireland"]),
                tier2,
            ).reason,
            "location_filter_tier1_only_location",
        )
        self.assertTrue(
            relevance_decision(
                _row("Strategic Operations Lead", ["Dublin, Ireland"]),
                tier1,
            ).should_evaluate
        )
        self.assertTrue(
            relevance_decision(
                _row(
                    "Strategic Operations Lead",
                    ["New York, United States", "London, United Kingdom"],
                ),
                tier2,
            ).should_evaluate
        )

    def test_us_location_gate_requires_tier1_sponsorship_and_exceptional_role(self) -> None:
        sponsored = relevance_decision(
            _row(
                "Strategic Operations Lead",
                ["New York, United States"],
                department="Strategy & Operations",
                description="Visa sponsorship available for exceptional candidates.",
            ),
            _company(tier=1),
        )
        no_sponsorship = relevance_decision(
            _row(
                "Strategic Operations Lead",
                ["New York, United States"],
                department="Strategy & Operations",
                description="Lead strategic operations programs.",
            ),
            _company(tier=1),
        )
        non_exceptional = relevance_decision(
            _row(
                "Payroll Manager",
                ["New York, United States"],
                department="Finance",
                description="Visa sponsorship available.",
            ),
            _company(tier=1),
        )

        self.assertTrue(sponsored.should_evaluate)
        self.assertEqual(
            no_sponsorship.reason,
            "location_filter_us_requires_tier1_sponsorship_exceptional_role",
        )
        self.assertEqual(
            non_exceptional.reason,
            "location_filter_us_requires_tier1_sponsorship_exceptional_role",
        )

    def test_relevance_gate_uses_title_department_not_description_for_positive_match(
        self,
    ) -> None:
        company = _company(target_locations=["London / UK"])
        payroll = relevance_decision(
            _row(
                "Payroll Manager",
                ["London, United Kingdom"],
                department="Finance",
                description=(
                    "Partner with strategy and operations teams on transformation "
                    "program reporting."
                ),
            ),
            company,
        )
        ambiguous = relevance_decision(
            _row(
                "Operations Manager",
                ["London, United Kingdom"],
                department="Operations",
                description="Own operational execution for a broad business area.",
            ),
            company,
        )

        self.assertFalse(payroll.should_evaluate)
        self.assertEqual(payroll.reason, "excluded_title_department_function")
        self.assertTrue(ambiguous.should_evaluate)
        self.assertEqual(ambiguous.reason, "ambiguous_title_department_routed_to_llm")


def _company(
    *,
    name: str = "ExampleCo",
    tier: int = 1,
    warm_path: bool = False,
    target_locations: list[str] | None = None,
) -> CompanyConfig:
    return CompanyConfig(
        name=name,
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
