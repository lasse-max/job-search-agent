from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import yaml

from app.config import (
    CONFIG_DIR,
    load_candidate_profile,
    load_location_policy,
    load_scoring_policy,
)
from app.services.evaluate import _feasibility, _role_family_fit, _weighted_fit_score


class ConfigLoadingTest(unittest.TestCase):
    def test_changing_scoring_yaml_changes_fit_score(self) -> None:
        path = _changed_yaml(
            "scoring_policy.yaml",
            lambda data: _set_family_only_weights(data),
        )
        policy = load_scoring_policy(path)
        dimensions = {
            "role_family_fit": 100,
            "evidence_strength": 50,
            "scope_seniority": 50,
            "gap_manageability": 50,
        }

        self.assertEqual(_weighted_fit_score(dimensions, policy), 100)

    def test_changing_location_yaml_changes_feasibility_reason(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            markets = data["markets"]
            assert isinstance(markets, dict)
            australia = markets["Australia"]
            assert isinstance(australia, dict)
            australia["notes"] = "Temporary policy note from test YAML."
            australia["expected_availability_date"] = "arrival_plus_6_months"

        path = _changed_yaml("location_policy.yaml", mutate)
        policy = load_location_policy(path)

        state, reason = _feasibility(["Sydney, Australia"], policy)

        self.assertEqual(state, "viable")
        self.assertIn("Temporary policy note from test YAML.", reason)
        self.assertIn("arrival_plus_6_months", reason)

    def test_changing_candidate_profile_yaml_changes_family_fit(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            patterns = data["role_family_patterns"]
            assert isinstance(patterns, dict)
            patterns["primary"] = [r"\bchief astronaut\b"]
            patterns["stretch"] = []

        path = _changed_yaml("candidate_profile.yaml", mutate)
        profile = load_candidate_profile(path)

        self.assertEqual(
            _role_family_fit(
                "Strategic Operations Manager",
                "Business Operations",
                "lead strategic operations programs",
                profile,
            ),
            58,
        )


def _changed_yaml(file_name: str, mutate) -> Path:
    source = CONFIG_DIR / file_name
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    mutate(data)
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / file_name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    _TEMP_DIRS.append(directory)
    return path


def _set_family_only_weights(data: dict[str, object]) -> None:
    dimensions = data["fit_dimensions"]
    assert isinstance(dimensions, dict)
    for name, raw_dimension in dimensions.items():
        assert isinstance(raw_dimension, dict)
        raw_dimension["weight"] = 100 if name == "role_family_fit" else 0


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
