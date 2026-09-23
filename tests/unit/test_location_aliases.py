from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from app.config import CONFIG_DIR, load_location_policy
from app.models import CompanyConfig
from app.services.evaluate import _feasibility, _location_gate_decision
from app.services.location_aliases import resolve_location_aliases


class LocationAliasesTest(unittest.TestCase):
    def test_districts_resolve_and_pass_gate_for_every_allowlisted_city(self) -> None:
        cases = {
            "Sydney": "Barangaroo",
            "Melbourne": "Docklands, VIC, Australia",
            "London": "Canary Wharf, UK",
            "Berlin": "Kreuzberg, Germany",
            "Munich": "Schwabing-Freimann, Germany",
            "Hamburg": "HafenCity, Germany",
            "Amsterdam": "Zuidas, Netherlands",
            "Paris": "La D\u00e9fense, France",
            "Copenhagen": "\u00d8restad, Denmark",
            "Zurich": "Oerlikon, Switzerland",
            "Lisbon": "Parque das Na\u00e7\u00f5es, Portugal",
            "Singapore": "one-north",
            "Perth": "Claisebrook, WA, Australia",
            "Brisbane": "Fortitude Valley, QLD, Australia",
        }
        policy = load_location_policy()
        self.assertEqual({entry.city for entry in policy.aliases}, set(cases))
        with (CONFIG_DIR / "location_policy.yaml").open(encoding="utf-8") as source:
            raw_policy = yaml.safe_load(source)
        self.assertEqual(set(cases), set(raw_policy["profile_display"]["allowed_metros"]))

        for city, location in cases.items():
            with self.subTest(city=city):
                expanded = resolve_location_aliases([location], policy)
                self.assertIn(city.casefold(), expanded[0].casefold())
                self.assertIsNone(_location_gate_decision(_row(location), _company(), policy))
                self.assertEqual(_feasibility([location], policy), _feasibility([city], policy))

    def test_barangaroo_is_expanded_before_gate_without_mutating_source(self) -> None:
        row = _row("Barangaroo, NSW 2000, Australia (Hybrid)")
        original = dict(row)
        locations = json.loads(row["locations_json"])
        expanded = resolve_location_aliases(locations)

        self.assertEqual(expanded, [f"{locations[0]} (Sydney)"])
        self.assertIsNone(_location_gate_decision(row, _company(), load_location_policy()))
        self.assertEqual(row, original)
        self.assertNotIn("Sydney", locations[0])

    def test_boundaries_homonyms_and_foreign_context_do_not_expand(self) -> None:
        cases = [
            "Barangarooville",
            "NewBarangaroo",
            "Barangaroo2",
            "Richmond, US",
            "Richmond, Virginia, United States",
            "Docklands",
            "Docklands, Ireland",
            "Docklands, Victoria, Canada",
            "Barangaroo, NSW, United States",
            "Barangaroo, NSW, Australia, Canada",
            "Barangaroo, Poland",
            "Canary Wharf, New York",
            "Zuidas, Singapore",
            "Fortitude Valley, California",
            "one-north, India",
        ]
        policy = load_location_policy()
        for location in cases:
            with self.subTest(location=location):
                self.assertEqual(resolve_location_aliases([location], policy), [location])

    def test_country_context_does_not_leak_between_posted_locations(self) -> None:
        locations = ["Docklands", "VIC, Australia", "Barangaroo, USA", "Barangaroo"]

        self.assertEqual(
            resolve_location_aliases(locations),
            ["Docklands", "VIC, Australia", "Barangaroo, USA", "Barangaroo (Sydney)"],
        )

    def test_aliases_are_config_driven_not_a_parallel_hardcoded_list(self) -> None:
        data = yaml.safe_load((CONFIG_DIR / "location_policy.yaml").read_text(encoding="utf-8"))
        data["location_aliases"]["Sydney"]["aliases"] = ["New Test District"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "location_policy.yaml"
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
            policy = load_location_policy(path)

        self.assertEqual(resolve_location_aliases(["Barangaroo"], policy), ["Barangaroo"])
        self.assertEqual(
            resolve_location_aliases(["New Test District, NSW"], policy),
            ["New Test District, NSW (Sydney)"],
        )
        self.assertIsNone(_location_gate_decision(_row("New Test District"), _company(), policy))
        self.assertIsNotNone(_location_gate_decision(_row("Barangaroo"), _company(), policy))

    def test_empty_alias_configuration_preserves_existing_location_behavior(self) -> None:
        policy = replace(load_location_policy(), aliases=())
        locations = ["Barangaroo", "London", "San Francisco, California"]

        self.assertEqual(resolve_location_aliases(locations, policy), locations)
        self.assertIsNotNone(_location_gate_decision(_row("Barangaroo"), _company(), policy))
        self.assertIsNone(_location_gate_decision(_row("London"), _company(), policy))

    def test_alias_expansion_is_idempotent(self) -> None:
        locations = ["Barangaroo", "Docklands, VIC", "Neu-Oerlikon, Switzerland"]

        expanded = resolve_location_aliases(locations)

        self.assertEqual(resolve_location_aliases(expanded), expanded)


def _row(location: str) -> dict[str, str]:
    return {
        "title": "Business Operations Manager",
        "department": "Strategy and Operations",
        "description_text": "Lead operational improvement programs.",
        "locations_json": json.dumps([location]),
    }


def _company() -> CompanyConfig:
    return CompanyConfig(
        name="ExampleCo",
        tier=2,
        enabled=True,
        ats_type="ashby",
        source_key="example",
        careers_url="https://example.com/careers",
        target_locations=["Sydney / Australia"],
        target_role_family_notes="Business operations",
        warm_path=False,
    )
