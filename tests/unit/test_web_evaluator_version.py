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


if __name__ == "__main__":
    unittest.main()
