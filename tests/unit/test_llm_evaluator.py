from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.config import load_candidate_profile
from app.models import CompanyConfig
from app.services.evaluate import HYBRID_EVALUATOR_VERSION, evaluate_role
from app.services.llm_evaluator import (
    ClaudeLLMProvider,
    DEFAULT_ESTIMATED_EVAL_COST_USD,
    LLMEvaluationOutput,
    LLMEvaluationResult,
    LLMRoleRequest,
    LLMProviderError,
    ModelSpendCapExceeded,
    ModelSpendTracker,
)


class LlmEvaluatorTest(unittest.TestCase):
    def test_llm_dimensions_feed_deterministic_final_score_and_band(self) -> None:
        row = _row("Strategic Operations Lead")
        company = _company()
        provider = FakeProvider(
            LLMEvaluationOutput.model_validate(
                {
                    "role_family_fit": 92,
                    "evidence_strength": 88,
                    "scope_seniority": 84,
                    "gap_manageability": 80,
                    "confidence": 0.81,
                    "advisory_recommendation": "skip",
                    "alignments": [
                        {
                            "job_requirement": "Lead strategy operations programs",
                            "candidate_evidence": "Google transformation work",
                            "evidence_strength": "strong",
                        }
                    ],
                    "gaps": [
                        {
                            "gap": "No direct AI-lab operating cadence",
                            "severity": "medium",
                            "mitigation": "Anchor in Google scale and rollout evidence",
                        }
                    ],
                    "uncertainties": ["JD does not state team size."],
                    "summary": "Strong strategy and operations match.",
                }
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            tracker = ModelSpendTracker(ledger_path=Path(directory) / "spend.json")
            evaluation = evaluate_role(
                row,
                company,
                llm_provider=provider,
                spend_tracker=tracker,
            )

        self.assertEqual(evaluation.recommendation, "apply_now")
        self.assertGreaterEqual(evaluation.role_fit_score, 80)
        self.assertEqual(evaluation.confidence, 0.81)
        self.assertEqual(evaluation.provenance["model_version"], "fake-claude")
        self.assertEqual(evaluation.provenance["evaluator_version"], HYBRID_EVALUATOR_VERSION)
        self.assertEqual(evaluation.provenance["llm_advisory_recommendation"], "skip")
        self.assertEqual(provider.calls, 1)

    def test_cost_cap_halts_before_provider_call(self) -> None:
        row = _row("Strategic Operations Lead")
        provider = FakeProvider(_valid_output())
        with tempfile.TemporaryDirectory() as directory:
            tracker = ModelSpendTracker(
                ledger_path=Path(directory) / "spend.json",
                monthly_cap_usd=0.01,
                estimated_eval_cost_usd=0.02,
            )

            with self.assertRaises(ModelSpendCapExceeded):
                evaluate_role(
                    row,
                    _company(),
                    llm_provider=provider,
                    spend_tracker=tracker,
                )

        self.assertEqual(provider.calls, 0)

    def test_llm_reported_hard_requirement_is_code_enforced(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload["hard_blockers"] = [
            {
                "type": "disqualifying_hard_requirement",
                "evidence": "Minimum qualification: advanced Python programming required.",
            }
        ]
        provider = FakeProvider(
            LLMEvaluationOutput.model_validate(output_payload)
        )

        evaluation = evaluate_role(
            _row("Strategic Operations Lead"),
            _company(),
            llm_provider=provider,
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertEqual(evaluation.recommendation, "blocked")
        self.assertIn(
            "disqualifying_hard_requirement",
            [blocker.type for blocker in evaluation.hard_blockers],
        )

    def test_core_role_family_calibration_surfaces_conservative_llm_score(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 75,
                "evidence_strength": 35,
                "scope_seniority": 75,
                "gap_manageability": 40,
                "confidence": 0.25,
                "advisory_recommendation": "skip",
            }
        )
        provider = FakeProvider(LLMEvaluationOutput.model_validate(output_payload))

        evaluation = evaluate_role(
            _row("Sales Strategy and Operations, ANZ"),
            _company(),
            llm_provider=provider,
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertIn(evaluation.recommendation, {"apply_now", "consider"})
        self.assertGreaterEqual(evaluation.dimensions["evidence_strength"], 62)

    def test_low_priority_adjacent_function_is_capped_out_of_digest_surface(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 82,
                "evidence_strength": 75,
                "scope_seniority": 78,
                "gap_manageability": 72,
                "confidence": 0.82,
                "advisory_recommendation": "consider",
            }
        )
        row = _row("Senior Manager, Strategic Finance, Channel Sales")
        row["department"] = "Strategic Finance"
        row["description_text"] = (
            "Lead strategic finance and channel sales planning with finance technology "
            "stakeholders."
        )

        evaluation = evaluate_role(
            row,
            _company(),
            llm_provider=FakeProvider(LLMEvaluationOutput.model_validate(output_payload)),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertNotIn(evaluation.recommendation, {"apply_now", "consider"})

    def test_gate_penalties_cap_overgenerous_llm_fit(self) -> None:
        cases = (
            (
                "native_pm",
                "Product Manager, Consumer",
                "Product",
                "Own product roadmap, PRDs, experimentation, launch planning, and PM rituals.",
                ["London, United Kingdom"],
                _company(),
            ),
            (
                "marketing",
                "Senior Product Marketing Manager",
                "Marketing",
                "Own product marketing launches, messaging, campaigns, and demand generation.",
                ["London, United Kingdom"],
                _company(),
            ),
            (
                "off_location",
                "Strategic Operations Lead",
                "Strategy & Operations",
                "Lead strategic operations programs and executive cadence.",
                ["Toronto, Canada"],
                _company(),
            ),
            (
                "wrong_language",
                "Strategist, Agent Development (Spanish speaking)",
                "Product",
                "Lead agent strategy for customers. Spanish fluency required.",
                ["Madrid, Spain"],
                _company_targeting(["Madrid / Spain"]),
            ),
            (
                "defense",
                "Deployment Strategist - AUS Government",
                "Professional Services",
                "Lead deployment strategy for public sector customers.",
                ["Sydney, Australia"],
                _company_targeting(["Sydney / Australia"]),
            ),
            (
                "pre_sales",
                "Principal Client Value Partner",
                "Value Engineering",
                "Own value selling, pre-sales discovery, customer demos, and value cases.",
                ["London, United Kingdom"],
                _company(),
            ),
        )

        for name, title, department, description, locations, company in cases:
            with self.subTest(name=name):
                output_payload = _valid_output().model_dump()
                output_payload.update(
                    {
                        "role_family_fit": 90,
                        "evidence_strength": 88,
                        "scope_seniority": 86,
                        "gap_manageability": 84,
                        "confidence": 0.84,
                        "advisory_recommendation": "apply_now",
                    }
                )
                row = _row(title)
                row["department"] = department
                row["description_text"] = description
                row["locations_json"] = json.dumps(locations)

                evaluation = evaluate_role(
                    row,
                    company,
                    llm_provider=FakeProvider(LLMEvaluationOutput.model_validate(output_payload)),
                    spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
                )

                self.assertEqual(evaluation.recommendation, "skip")
                self.assertLess(evaluation.role_fit_score, 60)

    def test_required_credential_and_salary_band_reduce_llm_fit(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 92,
                "evidence_strength": 88,
                "scope_seniority": 84,
                "gap_manageability": 80,
                "confidence": 0.81,
                "advisory_recommendation": "apply_now",
            }
        )
        provider_output = LLMEvaluationOutput.model_validate(output_payload)

        credential_row = _row("Strategic Operations Lead")
        credential_row["description_text"] = (
            "Requirements: PMP certification and intermediate platform certification "
            "within six months. Lead strategic operations programs."
        )
        credential = evaluate_role(
            credential_row,
            _company(),
            llm_provider=FakeProvider(provider_output),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        lead_row = _row("Lead, Strategic Operations")
        lead_row["description_text"] = (
            "Lead strategic operations programs and executive cadence. "
            "Annual base salary range is $260,000 - $320,000 USD."
        )
        senior_ic = evaluate_role(
            lead_row,
            _company(),
            llm_provider=FakeProvider(provider_output),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        director_row = _row("Director, Strategic Operations")
        director_row["description_text"] = (
            "Lead strategic operations programs and executive cadence. "
            "Annual base salary range is $260,000 - $320,000 USD."
        )
        director = evaluate_role(
            director_row,
            _company(),
            llm_provider=FakeProvider(provider_output),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        allowance_row = _row("Strategic Operations Lead")
        allowance_row["description_text"] = (
            "Lead strategic operations programs and executive cadence. "
            "Competitive cash salary and equity. Food benefit: £200 monthly allowance."
        )
        allowance = evaluate_role(
            allowance_row,
            _company(),
            llm_provider=FakeProvider(provider_output),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertLess(credential.role_fit_score, 70)
        self.assertNotIn(credential.recommendation, {"apply_now", "consider"})
        self.assertEqual(senior_ic.recommendation, "stretch")
        self.assertGreaterEqual(senior_ic.role_fit_score, 60)
        self.assertLess(senior_ic.role_fit_score, 70)
        self.assertEqual(director.recommendation, "skip")
        self.assertLess(director.role_fit_score, 60)
        self.assertEqual(allowance.recommendation, "apply_now")

    def test_below_level_title_caps_only_when_scope_is_missing(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 88,
                "evidence_strength": 82,
                "scope_seniority": 80,
                "gap_manageability": 76,
                "confidence": 0.78,
                "advisory_recommendation": "apply_now",
            }
        )
        provider_output = LLMEvaluationOutput.model_validate(output_payload)

        sparse = _row("GTM Strategy & Operations Analyst")
        sparse["description_text"] = "Support reporting and dashboards for the GTM team."
        scoped = _row("Strategy and Operations Associate")
        scoped["description_text"] = (
            "Own cross-functional strategic program delivery and drive executive rhythm "
            "with senior stakeholders."
        )

        sparse_eval = evaluate_role(
            sparse,
            _company(),
            llm_provider=FakeProvider(provider_output),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )
        scoped_eval = evaluate_role(
            scoped,
            _company(),
            llm_provider=FakeProvider(provider_output),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertEqual(sparse_eval.recommendation, "skip")
        self.assertLess(sparse_eval.role_fit_score, 60)
        self.assertNotEqual(scoped_eval.recommendation, "skip")
        self.assertGreaterEqual(scoped_eval.role_fit_score, 70)

    def test_domain_mentions_do_not_cap_core_revenue_strategy_role(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 87,
                "evidence_strength": 82,
                "scope_seniority": 79,
                "gap_manageability": 75,
                "confidence": 0.82,
                "advisory_recommendation": "apply_now",
            }
        )
        row = _row("Senior Manager, Revenue Strategy & Operations")
        row["department"] = "Strategy & Operations"
        row["description_text"] = (
            "Lead EMEA Revenue Strategy & Operations for a global banking and "
            "payments platform with embedded finance products."
        )

        evaluation = evaluate_role(
            row,
            _company(),
            llm_provider=FakeProvider(LLMEvaluationOutput.model_validate(output_payload)),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertEqual(evaluation.recommendation, "apply_now")

    def test_degree_only_hard_blocker_is_not_enforced_for_deployment_strategist(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 72,
                "evidence_strength": 65,
                "scope_seniority": 75,
                "gap_manageability": 62,
                "confidence": 0.72,
                "advisory_recommendation": "consider",
                "hard_blockers": [
                    {
                        "type": "disqualifying_hard_requirement",
                        "evidence": (
                            "JD states 'Required Engineering or computer science degree "
                            "from top tier institution.'"
                        ),
                    }
                ],
            }
        )
        row = _row("AI Deployment Strategist")
        row["department"] = "Professional Services"
        row["description_text"] = (
            "Work directly with customers to translate business problems into models. "
            "What we're looking for Required Engineering or computer science degree "
            "from top tier institution. Proficiency with formulas, logic, and "
            "structured modeling."
        )

        evaluation = evaluate_role(
            row,
            _company(),
            llm_provider=FakeProvider(LLMEvaluationOutput.model_validate(output_payload)),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertNotEqual(evaluation.recommendation, "blocked")
        self.assertEqual(evaluation.hard_blockers, [])

    def test_technical_depth_hard_blocker_is_enforced_for_deployment_strategist(
        self,
    ) -> None:
        evidence_cases = (
            (
                "requires",
                "JD states 'This role requires production software development in customer environments.'",
            ),
            (
                "mandatory",
                "JD states 'Mandatory advanced Python programming for deployment architecture.'",
            ),
            (
                "must",
                "JD states 'You must own deep ML engineering work for customer deployments.'",
            ),
            (
                "central duty",
                "JD states 'Production coding is the central duty of this deployment role.'",
            ),
        )

        for name, evidence in evidence_cases:
            with self.subTest(name=name):
                output_payload = _valid_output().model_dump()
                output_payload.update(
                    {
                        "role_family_fit": 72,
                        "evidence_strength": 65,
                        "scope_seniority": 75,
                        "gap_manageability": 62,
                        "confidence": 0.72,
                        "advisory_recommendation": "consider",
                        "hard_blockers": [
                            {
                                "type": "disqualifying_hard_requirement",
                                "evidence": evidence,
                            }
                        ],
                    }
                )
                row = _row("AI Deployment Strategist")
                row["department"] = "Professional Services"
                row["description_text"] = (
                    "Work directly with customers to translate business problems into "
                    "AI deployment plans."
                )

                evaluation = evaluate_role(
                    row,
                    _company(),
                    llm_provider=FakeProvider(
                        LLMEvaluationOutput.model_validate(output_payload)
                    ),
                    spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
                )

                self.assertEqual(evaluation.recommendation, "blocked")
                self.assertIn(
                    "disqualifying_hard_requirement",
                    [blocker.type for blocker in evaluation.hard_blockers],
                )

    def test_core_family_floor_does_not_rescue_plain_revenue_ops(self) -> None:
        output_payload = _valid_output().model_dump()
        output_payload.update(
            {
                "role_family_fit": 45,
                "evidence_strength": 15,
                "scope_seniority": 45,
                "gap_manageability": 20,
                "confidence": 0.25,
                "advisory_recommendation": "skip",
            }
        )

        evaluation = evaluate_role(
            _row("Manager, Revenue Operations"),
            _company(),
            llm_provider=FakeProvider(LLMEvaluationOutput.model_validate(output_payload)),
            spend_tracker=ModelSpendTracker(monthly_cap_usd=None),
        )

        self.assertLess(evaluation.dimensions["role_family_fit"], 82)
        self.assertNotIn(evaluation.recommendation, {"apply_now", "consider"})

    def test_default_model_cost_estimate_stays_below_one_cent(self) -> None:
        self.assertLess(DEFAULT_ESTIMATED_EVAL_COST_USD, 0.01)

    def test_claude_provider_rejects_malformed_structured_output(self) -> None:
        provider = ClaudeLLMProvider(api_key="test-key", model="fake-model")
        request = LLMRoleRequest(
            row=_row("Strategic Operations Lead"),
            company=_company(),
            profile=load_candidate_profile(),
        )
        payload = _claude_payload(
            {
                "role_family_fit": 101,
                "evidence_strength": 80,
                "scope_seniority": 80,
                "gap_manageability": 80,
                "confidence": 0.5,
                "advisory_recommendation": "consider",
                "alignments": [],
                "gaps": [],
                "uncertainties": [],
                "summary": "Bad score should fail.",
            }
        )

        with patch("app.services.llm_evaluator.httpx.post", return_value=FakeHttpResponse(payload)):
            with self.assertRaises(LLMProviderError):
                provider.evaluate(request)

    def test_validates_summary_with_realistic_verbose_bound(self) -> None:
        payload = _valid_output().model_dump()
        payload["summary"] = "A" * 1800

        output = LLMEvaluationOutput.model_validate(payload)

        self.assertEqual(len(output.summary), 1800)

    def test_validates_verbose_hard_blocker_evidence(self) -> None:
        payload = _valid_output().model_dump()
        payload["hard_blockers"] = [
            {
                "type": "disqualifying_hard_requirement",
                "evidence": "Bachelor's degree in Computer Science required. " * 15,
            }
        ]

        output = LLMEvaluationOutput.model_validate(payload)

        self.assertEqual(output.hard_blockers[0].type, "disqualifying_hard_requirement")

    def test_validates_five_gap_model_output(self) -> None:
        payload = _valid_output().model_dump()
        payload["gaps"] = [
            {
                "gap": f"Gap {index}",
                "severity": "medium",
                "mitigation": "Use adjacent strategy and operations evidence.",
            }
            for index in range(5)
        ]

        output = LLMEvaluationOutput.model_validate(payload)

        self.assertEqual(len(output.gaps), 5)

    def test_normalizes_empty_string_hard_blockers(self) -> None:
        payload = _valid_output().model_dump()
        payload["hard_blockers"] = ""

        output = LLMEvaluationOutput.model_validate(payload)

        self.assertEqual(output.hard_blockers, [])

    def test_coerces_json_encoded_list_fields_from_live_response(self) -> None:
        payload = _valid_output().model_dump()
        payload["alignments"] = json.dumps(payload["alignments"], indent=2)
        payload["gaps"] = json.dumps(payload["gaps"], indent=2)
        payload["uncertainties"] = json.dumps(payload["uncertainties"], indent=2)

        output = LLMEvaluationOutput.model_validate(payload)

        self.assertEqual(output.alignments[0].job_requirement, "Lead strategy operations programs")
        self.assertEqual(output.gaps[0].gap, "No direct AI-lab operating cadence")
        self.assertEqual(output.uncertainties, ["JD does not state team size."])

    def test_claude_provider_retries_transient_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = ClaudeLLMProvider(
                api_key="test-key",
                model="fake-model",
                cache_dir=Path(directory),
            )
            request = LLMRoleRequest(
                row=_row("Strategic Operations Lead"),
                company=_company(),
                profile=load_candidate_profile(),
            )
            payload = _claude_payload(_valid_output().model_dump())

            with (
                patch(
                    "app.services.llm_evaluator.httpx.post",
                    side_effect=[
                        httpx.TimeoutException("timed out"),
                        FakeHttpResponse(payload),
                    ],
                ) as post,
                patch("app.services.llm_evaluator.time.sleep") as sleep,
            ):
                result = provider.evaluate(request)

        self.assertEqual(result.output.summary, "Strong strategy and operations match.")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()

    def test_claude_provider_caches_valid_response_by_material_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = ClaudeLLMProvider(
                api_key="test-key",
                model="fake-model",
                cache_dir=Path(directory),
            )
            request = LLMRoleRequest(
                row=_row("Strategic Operations Lead"),
                company=_company(),
                profile=load_candidate_profile(),
            )
            payload = _claude_payload(_valid_output().model_dump())

            with patch(
                "app.services.llm_evaluator.httpx.post",
                return_value=FakeHttpResponse(payload),
            ) as post:
                first = provider.evaluate(request)
                second = provider.evaluate(request)

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(second.output.summary, "Strong strategy and operations match.")


class FakeProvider:
    model_version = "fake-claude"

    def __init__(self, output: LLMEvaluationOutput) -> None:
        self.output = output
        self.calls = 0

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        self.calls += 1
        return LLMEvaluationResult(
            output=self.output,
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cost_usd=0.001,
        )


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


def _valid_output() -> LLMEvaluationOutput:
    return LLMEvaluationOutput.model_validate(
        {
            "role_family_fit": 92,
            "evidence_strength": 88,
            "scope_seniority": 84,
            "gap_manageability": 80,
            "confidence": 0.81,
            "advisory_recommendation": "apply_now",
            "alignments": [
                {
                    "job_requirement": "Lead strategy operations programs",
                    "candidate_evidence": "Google transformation work",
                    "evidence_strength": "strong",
                }
            ],
            "gaps": [
                {
                    "gap": "No direct AI-lab operating cadence",
                    "severity": "medium",
                    "mitigation": "Anchor in Google scale and rollout evidence",
                }
            ],
            "uncertainties": ["JD does not state team size."],
            "summary": "Strong strategy and operations match.",
        }
    )


def _claude_payload(tool_input: dict[str, object]) -> dict[str, object]:
    return {
        "content": [
            {
                "type": "tool_use",
                "name": "submit_role_evaluation",
                "input": tool_input,
            }
        ],
        "usage": {"input_tokens": 1000, "output_tokens": 500},
    }


def _company() -> CompanyConfig:
    return CompanyConfig(
        name="ExampleCo",
        tier=1,
        enabled=True,
        ats_type="manual",
        source_key="example",
        careers_url="https://example.com",
        target_locations=["London / UK"],
        target_role_family_notes="Strategy and operations",
        warm_path=False,
    )


def _company_targeting(target_locations: list[str]) -> CompanyConfig:
    company = _company()
    return CompanyConfig(
        name=company.name,
        tier=company.tier,
        enabled=company.enabled,
        ats_type=company.ats_type,
        source_key=company.source_key,
        careers_url=company.careers_url,
        target_locations=target_locations,
        target_role_family_notes=company.target_role_family_notes,
        warm_path=company.warm_path,
    )


def _row(title: str) -> dict[str, str]:
    return {
        "title": title,
        "locations_json": json.dumps(["London, United Kingdom"]),
        "department": "Strategy & Operations",
        "employment_type": "Full-time",
        "description_text": (
            "Lead strategy and operations programs for cross-functional stakeholders. "
            "Own executive cadence, transformation, and program delivery."
        ),
        "source_url": "https://example.com/job",
    }


if __name__ == "__main__":
    unittest.main()
