import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from scripts.diagnose_ingestion import main


class IngestionDiagnosticTest(unittest.TestCase):
    def test_diagnostic_forces_read_only_and_only_issues_reads(self) -> None:
        connection = MagicMock()
        cursor = connection.execute.return_value
        cursor.fetchone.side_effect = [("on",), (True, True, False), (False, None, None)]
        cursor.fetchall.return_value = [("failed", 1, 350, 1)]
        with patch.dict("os.environ", {"JOB_AGENT_DATABASE_URL": "private-connection"}):
            with patch("scripts.diagnose_ingestion.psycopg.connect") as connect:
                connect.return_value.__enter__.return_value = connection
                output = io.StringIO()
                with redirect_stdout(output):
                    result = main()
        self.assertEqual(result, 0)
        self.assertIs(connection.read_only, True)
        self.assertIn("default_transaction_read_only=on", connect.call_args.kwargs["options"])
        self.assertTrue(all(
            call.args[0].lstrip().startswith(("SELECT", "SHOW"))
            for call in connection.execute.call_args_list
        ))
        self.assertIn('"http_400_count": 1', output.getvalue())
        self.assertNotIn("private-connection", output.getvalue())

    def test_diagnostic_redacts_connection_errors(self) -> None:
        with patch.dict("os.environ", {"JOB_AGENT_DATABASE_URL": "private-connection"}):
            with patch("scripts.diagnose_ingestion.psycopg.connect", side_effect=RuntimeError("secret host and password")):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(), 1)
        self.assertNotIn("secret host", output.getvalue())
