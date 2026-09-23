from __future__ import annotations

from dataclasses import replace
import unittest

from app.adapters.utils import compact_text
from app.config import load_candidate_profile
from app.services.evaluate import (
    _government_defense_or_clearance_scope,
    _security_clearance_required,
    evaluate_role,
    has_disqualifying_hard_requirement,
    relevance_decision,
)
from tests.unit.test_evaluate import _company, _row


class RequirementScopeTest(unittest.TestCase):
    def test_live_company_legal_boilerplate_does_not_block_or_cap_business_role(self) -> None:
        # Minimal source excerpts; surrounding role text is synthetic.
        footers = {
            "ServiceNow": (
                "Additional Information\nExport Control Regulations\n"
                "For positions requiring controlled technology, including the U.S. "
                "Export Administration Regulations, the company may be required to obtain "
                "export control approval from government authorities for certain individuals."
            ),
            "Plaid": (
                "We do not discriminate based on military or veteran status, disability, "
                "or other applicable legally protected characteristics."
            ),
        }
        body = (
            "Responsibilities:\nLead strategic operations and executive planning.\n"
            "Qualifications:\nExperience in business strategy and program management.\n"
        )
        company = _company(name="Synthetic Employer", tier=2)
        base = evaluate_role(
            _row("Strategy & Operations Manager", ["London"], description=body),
            company, use_env_provider=False,
        )
        for source, footer in footers.items():
            for flatten in (False, True):
                with self.subTest(source=source, flattened=flatten):
                    text = body + footer
                    if flatten:
                        text = compact_text(text)
                    row = _row("Strategy & Operations Manager", ["London"], description=text)
                    self.assertTrue(relevance_decision(row, company).should_evaluate)
                    result = evaluate_role(row, company, use_env_provider=False)
                    self.assertFalse(result.hard_blockers)
                    self.assertEqual(result.role_fit_score, base.role_fit_score)
                    self.assertEqual(result.recommendation, base.recommendation)

    def test_company_sections_do_not_supply_role_requirements(self) -> None:
        company_text = (
            "About us: We serve government customers. Our product requires advanced "
            "Python programming and security clearance workflows. "
            "Responsibilities: Lead commercial strategy and operations. "
            "Qualifications: Business strategy experience."
        )
        self.assertFalse(_government_defense_or_clearance_scope(company_text))
        self.assertFalse(_security_clearance_required(company_text))
        self.assertFalse(has_disqualifying_hard_requirement(company_text))
        self.assertFalse(has_disqualifying_hard_requirement(
            "About us: Our platform requires an Engineering degree to develop, "
            "and you lead commercial planning."
        ))
        self.assertFalse(_security_clearance_required(
            "The product supports security clearance workflows."
        ))
        self.assertFalse(_government_defense_or_clearance_scope(
            "Our platform supports government customers and military teams."
        ))
        for requirement in (
            "You will lead deployments for government customers.",
            "You must obtain SC clearance and satisfy continuous UK residency.",
        ):
            with self.subTest(requirement=requirement):
                self.assertTrue(_government_defense_or_clearance_scope(
                    company_text + " Responsibilities: " + requirement
                ))

    def test_qualification_context_survives_long_lists_and_flattening(self) -> None:
        for separator in ("\n", " "):
            for requirement in (
                "Bachelor's degree in Computer Science.",
                "Production coding in customer environments.",
            ):
                with self.subTest(separator=separator, requirement=requirement):
                    text = separator.join([
                        "Qualifications:",
                        "Experience leading stakeholder workshops and cross-functional "
                        "programs, including executive reporting and commercial planning.",
                        requirement,
                        "Additional Information: Our product supports diverse industries.",
                    ])
                    self.assertTrue(has_disqualifying_hard_requirement(text))

    def test_genuine_headingless_and_title_requirements_still_block(self) -> None:
        for text in (
            "Requires SC clearance and continuous UK residency.",
            "Additional Information: This position requires SC clearance.",
            "Additional Information: All employees must obtain SC clearance.",
            "Additional Information: Employment is contingent upon obtaining SC clearance.",
            "Must have experience serving government customers.",
            "You will lead deployments for military customers.",
        ):
            with self.subTest(text=text):
                self.assertTrue(_government_defense_or_clearance_scope(text))
        self.assertTrue(_government_defense_or_clearance_scope(
            "Lead customer operations.", "Deployment Strategist - AUS Government"
        ))
        for text in (
            "Proficient in production coding.",
            "You must write production code.",
            "A degree in Computer Science is required.",
            "Additional Information: You must obtain a degree in Computer Science.",
            "Additional Information: Production coding is required.",
            "About us: We serve banking customers. You will write production code.",
        ):
            with self.subTest(text=text):
                self.assertTrue(has_disqualifying_hard_requirement(text))

    def test_inline_nouns_and_company_obligations_are_not_qualification_headings(self) -> None:
        for text in (
            "As a company, we must obtain government approval for exports.",
            "Our platform meets the requirements of government customers.",
            "About us: Our platform supports requirements for production coding.",
            "Company overview: Our platform supports customers with complex requirements, "
            "including production coding at scale. Job description: Lead business operations.",
            "Company overview: Our platform supports strict security requirements, "
            "including security clearance workflows. Job description: Lead business operations.",
        ):
            with self.subTest(text=text):
                self.assertFalse(_government_defense_or_clearance_scope(text))
                self.assertFalse(_security_clearance_required(text))
                self.assertFalse(has_disqualifying_hard_requirement(text))

    def test_preferences_negation_and_boilerplate_do_not_erase_real_requirements(self) -> None:
        for text in (
            "No production coding required.",
            "Production coding is not required for this role.",
            "Advanced programming skills are not required.",
            "This role does not involve production coding.",
            "Preferred qualifications: Production coding.",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_disqualifying_hard_requirement(text))
                self.assertTrue(has_disqualifying_hard_requirement(
                    text + " Requirements: Advanced Python programming is mandatory."
                ))
        self.assertFalse(_government_defense_or_clearance_scope(
            "Prior experience with defense or sovereign cloud environments is a plus."
        ))
        self.assertTrue(_government_defense_or_clearance_scope(
            "Qualifications: You must obtain SC clearance. "
            "Additional information: We do not discriminate based on military status."
        ))

    def test_responsibilities_are_not_mandatory_degrees_and_graded_plus_stays_optional(self) -> None:
        self.assertFalse(has_disqualifying_hard_requirement(
            "Responsibilities: Partner with colleagues with a degree in Computer Science."
        ))
        for heading in ("Responsibilities:", "WHAT YOU'LL BRING:", "Qualifications:"):
            for qualifier in ("strong", "definite", "big", "significant"):
                with self.subTest(heading=heading, qualifier=qualifier):
                    text = f"{heading} A degree in Computer Science is a {qualifier} plus."
                    self.assertFalse(has_disqualifying_hard_requirement(text))
                    self.assertTrue(has_disqualifying_hard_requirement(
                        text + " You must write production code."
                    ))
            optional_degree = (
                f"{heading} Degree in Computer Science, Engineering, "
                "or equivalent practical experience is a strong plus"
            )
            self.assertFalse(has_disqualifying_hard_requirement(optional_degree))
            self.assertTrue(has_disqualifying_hard_requirement(
                optional_degree + ", but proficient production coding is mandatory."
            ))

    def test_must_have_context_is_config_driven_and_local(self) -> None:
        profile = load_candidate_profile()
        custom = replace(profile, disqualifying_hard_requirements=replace(
            profile.disqualifying_hard_requirements,
            must_have_context_patterns=(r"\bprerequisite\b",),
        ))
        self.assertTrue(has_disqualifying_hard_requirement(
            "A degree in Computer Science is a prerequisite.", custom,
        ))
        self.assertFalse(has_disqualifying_hard_requirement(
            "A degree in Computer Science is required.", custom,
        ))
        self.assertFalse(_government_defense_or_clearance_scope(
            "Required business planning experience " + "with commercial teams " * 20
            + "and awareness of government policies."
        ))
        self.assertFalse(has_disqualifying_hard_requirement(
            "Required business planning experience " + "with commercial teams " * 20
            + "and awareness of a degree in Computer Science."
        ))
