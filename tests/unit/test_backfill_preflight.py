import io
from contextlib import redirect_stdout
from unittest.mock import patch
import unittest

from app.postgres import PostgresConnection
from app.services.scheduled_scan import BackfillPlan
from scripts.preflight_backfill import main


class BackfillPreflightTest(unittest.TestCase):
    def test_postgres_read_only_is_enforced_before_any_work(self) -> None:
        with patch("psycopg.connect") as connect:
            connect.return_value.execute.return_value.fetchone.return_value = ("on",)
            conn = PostgresConnection("secret", read_only=True)
            self.assertIs(connect.return_value.read_only, True)
            connect.return_value.execute.assert_called_once_with("SHOW transaction_read_only")
            conn.close()
        with patch("psycopg.connect") as connect:
            connect.return_value.execute.return_value.fetchone.return_value = ("off",)
            with self.assertRaisesRegex(RuntimeError, "read-only"):
                PostgresConnection("secret", read_only=True)
            connect.return_value.close.assert_called_once()

    def test_preflight_reports_counts_without_scanning_or_leaking_connection(self) -> None:
        output = io.StringIO()
        with patch.dict("os.environ", {"JOB_AGENT_DATABASE_URL": "secret"}), \
             patch("scripts.preflight_backfill.PostgresConnection") as connect, \
             patch("scripts.preflight_backfill.plan_stale_backfill_for_connection",
                   return_value=BackfillPlan(3, 60, 0.012, 21)), redirect_stdout(output):
            self.assertEqual(main(), 0)
            connect.assert_called_once_with("secret", read_only=True)
            connect.return_value.close.assert_called_once()
        self.assertIn('"item_count": 3', output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_preflight_redacts_errors(self) -> None:
        output = io.StringIO()
        with patch.dict("os.environ", {"JOB_AGENT_DATABASE_URL": "secret"}), \
             patch("scripts.preflight_backfill.PostgresConnection",
                   side_effect=RuntimeError("secret host password")), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertNotIn("secret", output.getvalue())
