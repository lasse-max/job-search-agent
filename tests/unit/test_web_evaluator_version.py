from __future__ import annotations

from pathlib import Path
import re
import unittest

from app.services.evaluate import HYBRID_EVALUATOR_VERSION


class WebEvaluatorVersionTest(unittest.TestCase):
    def test_web_current_evaluator_version_matches_python_source(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        web_data_file = repo_root / "web" / "lib" / "data" / "calibrated-evaluations.ts"
        source = web_data_file.read_text(encoding="utf-8")

        match = re.search(
            r'CURRENT_EVALUATOR_VERSION\s*=\s*"([^"]+)"',
            source,
        )

        self.assertIsNotNone(match, "web evaluator version constant was not found")
        self.assertEqual(match.group(1), HYBRID_EVALUATOR_VERSION)

    def test_estimated_level_and_location_dedup_are_rendered_from_stored_evaluation(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        data_source = (
            repo_root / "web" / "lib" / "data" / "calibrated-evaluations.ts"
        ).read_text(encoding="utf-8")
        ui_source = (
            repo_root / "web" / "app" / "potential-matches-client.tsx"
        ).read_text(encoding="utf-8")

        for field in ("estimated_level", "level_confidence", "level_rationale"):
            self.assertIn(field, data_source)
        self.assertIn("collapseLocationVariants", data_source)
        self.assertIn("stripLocationSuffix", data_source)
        self.assertIn("isLocationVariant", data_source)
        self.assertIn("materialSignature", data_source)
        self.assertIn("estimatedLevel: role.estimatedLevel", data_source)
        self.assertIn("blockers: [...role.hardBlockers].sort()", data_source)
        self.assertIn("|job:${role.id}`", data_source)
        self.assertIn("est. {role.estimatedLevel} ▲ above band", ui_source)
        self.assertIn("Estimated level:", ui_source)


if __name__ == "__main__":
    unittest.main()
