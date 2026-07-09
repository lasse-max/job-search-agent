from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import (
    get_digest_rows,
    init_db,
    latest_scan_reach,
    latest_source_failures,
    record_source_run,
)
from app.services.digest import render_html, render_text
from app.services.evaluate import HYBRID_EVALUATOR_VERSION
from app.services.manual_intake import add_text_intake
from app.services.notifications import EmailMessage, EmailSendResult, deliver_digest


JOB_TEXT = """Company: ExampleCo
Title: Strategic Operations Manager
Location: Munich, Germany
Department: Strategy & Operations

Lead strategy and operations programs for cross-functional stakeholders.
Own executive rhythm, customer operations, transformation work, and program delivery.
"""


SECOND_JOB_TEXT = """Company: SecondCo
Title: Business Operations Lead
Location: London, United Kingdom
Department: Business Operations

Lead business operations programs, executive reporting, and cross-functional planning.
"""


class NotificationDeliveryTest(unittest.TestCase):
    def test_no_api_key_writes_local_digest_and_records_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            add_text_intake(JOB_TEXT, db_path=db_path, source_url="https://example.com/job")
            conn = _connect(db_path)

            with patch.dict("os.environ", {"RESEND_API_KEY": ""}):
                result = deliver_digest(conn, output_dir=output_dir)

            self.assertEqual(result.status, "fallback")
            self.assertEqual(result.recipient, "")
            self.assertTrue((output_dir / "latest_digest.html").exists())
            self.assertIn(
                "DEGRADED",
                (output_dir / "latest_digest.html").read_text(encoding="utf-8"),
            )
            notification = conn.execute("SELECT * FROM notifications").fetchone()
            self.assertEqual(notification["status"], "fallback")
            self.assertEqual(notification["type"], "digest")

    def test_since_last_digest_includes_only_newer_evaluations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            first = add_text_intake(
                JOB_TEXT,
                db_path=db_path,
                source_url="https://example.com/first",
            )
            second = add_text_intake(
                SECOND_JOB_TEXT,
                db_path=db_path,
                source_url="https://example.com/second",
            )
            conn = _connect(db_path)
            conn.execute(
                "UPDATE role_evaluations SET created_at = ? WHERE job_posting_id = ?",
                ("2026-06-24T10:00:00+00:00", first.job_id),
            )
            conn.execute(
                "UPDATE role_evaluations SET created_at = ? WHERE job_posting_id = ?",
                ("2026-06-24T12:00:00+00:00", second.job_id),
            )
            conn.execute(
                """
                INSERT INTO notifications (type, payload_hash, sent_at, status, error_summary)
                VALUES ('digest', 'older-payload', '2026-06-24T11:00:00+00:00', 'sent', NULL)
                """
            )
            conn.commit()
            _mark_non_fallback_evaluations(conn)
            provider = FakeProvider()

            result = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(result.status, "sent")
            self.assertEqual(result.role_count, 1)
            self.assertEqual(result.calibration_count, 1)
            self.assertEqual(len(provider.messages), 1)
            self.assertIn(
                "Top open roles by fit — may repeat",
                provider.messages[0].html_body,
            )
            self.assertIn("Strategic Operations Manager", provider.messages[0].html_body)
            self.assertIn("Business Operations Lead", provider.messages[0].html_body)

    def test_provider_without_recipient_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            add_text_intake(JOB_TEXT, db_path=db_path, source_url="https://example.com/job")
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(conn)
            provider = FakeProvider()

            result = deliver_digest(conn, output_dir=output_dir, provider=provider)

            self.assertEqual(result.status, "failed")
            self.assertIn("DIGEST_RECIPIENT_EMAIL", result.error_summary or "")
            self.assertEqual(provider.messages, [])
            self.assertTrue((output_dir / "latest_digest.html").exists())

    def test_failures_are_sent_even_when_payload_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            conn = _connect(db_path)
            _insert_failed_source(conn)
            provider = FakeProvider()

            first = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )
            second = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(first.status, "sent")
            self.assertEqual(second.status, "sent")
            self.assertEqual(first.failure_count, 1)
            self.assertEqual(second.failure_count, 1)
            self.assertEqual(len(provider.messages), 2)

    def test_disabled_degraded_source_is_not_reported_as_latest_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            conn = _connect(db_path)
            _insert_disabled_degraded_source(conn)

            self.assertEqual(latest_source_failures(conn), [])

    def test_no_change_digest_is_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            conn = _connect(db_path)
            conn.execute(
                """
                INSERT INTO notifications (type, payload_hash, sent_at, status, error_summary)
                VALUES ('digest', 'older-payload', '2999-01-01T00:00:00+00:00', 'sent', NULL)
                """
            )
            conn.commit()
            provider = FakeProvider()

            result = deliver_digest(
                conn,
                output_dir=Path(directory) / "output",
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(result.status, "suppressed_no_change")
            self.assertEqual(provider.messages, [])

    def test_identical_role_digest_is_not_resent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            for index in range(5):
                job = add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/duplicate-{index:02d}",
                )
                conn = _connect(db_path)
                conn.execute(
                    "UPDATE role_evaluations SET created_at = ? WHERE job_posting_id = ?",
                    ("2026-06-24T10:00:00+00:00", job.job_id),
                )
                conn.commit()
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
            )
            provider = FakeProvider()

            first = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )
            conn.execute(
                "UPDATE notifications SET sent_at = ? WHERE payload_hash = ?",
                ("2026-06-24T09:00:00+00:00", first.payload_hash),
            )
            conn.commit()
            second = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(first.status, "sent")
            self.assertEqual(second.status, "suppressed_duplicate")
            self.assertEqual(first.role_count, 5)
            self.assertEqual(len(provider.messages), 1)

    def test_provider_sends_degraded_fallback_evaluator_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            for index in range(30):
                add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/fallback-{index:02d}",
                )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
                mark_non_fallback=False,
            )
            provider = FakeProvider()

            result = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(result.status, "sent")
            self.assertEqual(result.role_count, 25)
            self.assertIn("DEGRADED", result.subject)
            self.assertEqual(len(provider.messages), 1)
            self.assertIn("DEGRADED", provider.messages[0].html_body)
            self.assertEqual(
                provider.messages[0].text_body.count("Source: https://example.com/fallback-"),
                25,
            )
            self.assertIn("➕ 5 more", provider.messages[0].text_body)

    def test_normal_digest_appends_calibration_floor_when_strong_roles_are_thin(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            for index in range(6):
                add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/calibration-{index:02d}",
                )
            conn = _connect(db_path)
            for index, score in enumerate([10, 95, 40, 80, 70, 60]):
                _mark_non_fallback_evaluations(
                    conn,
                    title_contains=f"{index:02d}",
                    recommendation="skip",
                    role_fit_score=score,
                )

            text_body = render_text(get_digest_rows(conn), [])

            self.assertIn(
                "Top open roles by fit — may repeat",
                text_body,
            )
            self.assertIn("Source: https://example.com/calibration-01", text_body)
            self.assertIn("Source: https://example.com/calibration-03", text_body)
            self.assertNotIn("Source: https://example.com/calibration-00", text_body)
            self.assertEqual(text_body.count("Source: https://example.com/calibration-"), 5)

    def test_current_evaluator_filter_excludes_stale_llm_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            add_text_intake(
                JOB_TEXT,
                db_path=db_path,
                source_url="https://example.com/stale-version",
            )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
            )
            conn.execute(
                """
                UPDATE role_evaluations
                SET model_version = 'fake-claude|hybrid_claude_v1'
                """
            )
            conn.commit()

            self.assertEqual(len(get_digest_rows(conn)), 1)
            self.assertEqual(
                get_digest_rows(conn, evaluator_version=HYBRID_EVALUATOR_VERSION),
                [],
            )

    def test_degraded_fallback_digest_does_not_add_calibration_floor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            for index in range(6):
                add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/degraded-calibration-{index:02d}",
                )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="skip",
                role_fit_score=90,
                mark_non_fallback=False,
            )

            text_body = render_text(get_digest_rows(conn), [])

            self.assertIn("DEGRADED", text_body)
            self.assertNotIn("Top open roles by fit", text_body)

    def test_degraded_since_last_digest_does_not_calibrate_from_valid_open_pool(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            old_job_ids = []
            for index in range(5):
                job = add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/older-valid-{index:02d}",
                )
                old_job_ids.append(job.job_id)
            conn = _connect(db_path)
            for job_id in old_job_ids:
                conn.execute(
                    "UPDATE role_evaluations SET created_at = ? WHERE job_posting_id = ?",
                    ("2026-06-24T10:00:00+00:00", job_id),
                )
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
            )
            conn.execute(
                """
                INSERT INTO notifications (type, payload_hash, sent_at, status, error_summary)
                VALUES ('digest', 'older-payload', '2026-06-24T11:00:00+00:00', 'sent', NULL)
                """
            )
            conn.commit()

            new_job = add_text_intake(
                _job_text(99),
                db_path=db_path,
                source_url="https://example.com/new-fallback",
            )
            conn = _connect(db_path)
            conn.execute(
                "UPDATE role_evaluations SET created_at = ? WHERE job_posting_id = ?",
                ("2026-06-24T12:00:00+00:00", new_job.job_id),
            )
            conn.commit()
            _mark_non_fallback_evaluations(
                conn,
                title_contains="99",
                recommendation="apply_now",
                role_fit_score=90,
                mark_non_fallback=False,
            )
            provider = FakeProvider()

            result = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(result.status, "sent")
            self.assertEqual(result.role_count, 1)
            self.assertEqual(result.calibration_count, 0)
            self.assertEqual(len(provider.messages), 1)
            text_body = provider.messages[0].text_body
            self.assertIn("DEGRADED", text_body)
            self.assertIn("Source: https://example.com/new-fallback", text_body)
            self.assertNotIn("Top open roles by fit", text_body)
            self.assertNotIn("Source: https://example.com/older-valid-", text_body)

    def test_quiet_cycle_sends_calibration_floor_and_may_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            for index in range(5):
                job = add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/quiet-calibration-{index:02d}",
                )
                conn = _connect(db_path)
                conn.execute(
                    "UPDATE role_evaluations SET created_at = ? WHERE job_posting_id = ?",
                    ("2026-06-24T10:00:00+00:00", job.job_id),
                )
                conn.commit()
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="skip",
                role_fit_score=80,
            )
            conn.execute(
                """
                INSERT INTO notifications (type, payload_hash, sent_at, status, error_summary)
                VALUES ('digest', 'older-payload', '2026-06-24T11:00:00+00:00', 'sent', NULL)
                """
            )
            conn.commit()
            provider = FakeProvider()

            first = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )
            second = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(first.status, "sent")
            self.assertEqual(second.status, "sent")
            self.assertEqual(first.role_count, 0)
            self.assertEqual(second.role_count, 0)
            self.assertEqual(first.calibration_count, 5)
            self.assertEqual(second.calibration_count, 5)
            self.assertIn("5 calibration sample roles", first.subject)
            self.assertEqual(len(provider.messages), 2)
            self.assertIn("Top open roles by fit", provider.messages[0].text_body)
            self.assertIn(
                "Source: https://example.com/quiet-calibration-00",
                provider.messages[0].text_body,
            )

    def test_provider_withholds_fallback_rows_when_valid_rows_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            add_text_intake(JOB_TEXT, db_path=db_path, source_url="https://example.com/valid")
            add_text_intake(
                SECOND_JOB_TEXT,
                db_path=db_path,
                source_url="https://example.com/fallback",
            )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                title_contains="Strategic Operations Manager",
                recommendation="apply_now",
                role_fit_score=90,
            )
            provider = FakeProvider()

            result = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(result.status, "sent")
            self.assertEqual(result.role_count, 1)
            self.assertEqual(len(provider.messages), 1)
            self.assertIn("Strategic Operations Manager", provider.messages[0].text_body)
            self.assertNotIn("Business Operations Lead", provider.messages[0].text_body)
            self.assertIn("Fallback rows withheld: 1", provider.messages[0].text_body)

    def test_email_digest_caps_at_25_and_adds_overflow_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "output"
            for index in range(30):
                add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/job-{index:02d}",
                )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
            )
            provider = FakeProvider()

            result = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=provider,
                recipient="owner@example.com",
            )

            self.assertEqual(result.status, "sent")
            self.assertEqual(result.role_count, 25)
            self.assertEqual(len(provider.messages), 1)
            self.assertEqual(
                provider.messages[0].text_body.count("Source: https://example.com/job-"),
                25,
            )
            self.assertIn("➕ 5 more", provider.messages[0].text_body)
            self.assertIn("view full list", provider.messages[0].text_body)

    def test_overflow_counts_only_surfaced_cards_not_low_priority_padding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            for index in range(48):
                add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/count-{index:02d}",
                )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="skip",
                role_fit_score=55,
            )
            for index in range(30):
                _mark_non_fallback_evaluations(
                    conn,
                    title_contains=f"{index:02d}",
                    recommendation="apply_now",
                    role_fit_score=90,
                )

            text_body = render_text(get_digest_rows(conn), [])

            rendered_cards = text_body.count("Source: https://example.com/count-")
            shown_match = re.search(r"Showing (\d+) of (\d+) roles", text_body)
            self.assertIsNotNone(shown_match)
            assert shown_match is not None
            self.assertEqual(int(shown_match.group(1)), rendered_cards)
            self.assertEqual((shown_match.group(1), shown_match.group(2)), ("25", "30"))
            self.assertIn("➕ 5 more", text_body)
            self.assertIn("Low-priority / blocked: 18 not expanded", text_body)
            self.assertNotIn("Showing 25 of 48", text_body)

    def test_renderers_self_cap_when_called_with_uncapped_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            for index in range(30):
                add_text_intake(
                    _job_text(index),
                    db_path=db_path,
                    source_url=f"https://example.com/render-{index:02d}",
                )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
            )
            raw_rows = get_digest_rows(conn)

            html_body = render_html(raw_rows, [])
            text_body = render_text(raw_rows, [])

            self.assertEqual(text_body.count("Source: https://example.com/render-"), 25)
            self.assertEqual(html_body.count('href="https://example.com/render-'), 25)
            self.assertIn("\n  Source: https://example.com/render-", text_body)
            self.assertIn("➕ 5 more", text_body)
            self.assertIn("➕ 5 more", html_body)

    def test_digest_headers_include_latest_scan_reach(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            add_text_intake(
                JOB_TEXT,
                db_path=db_path,
                source_url="https://example.com/scan-reach",
            )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="apply_now",
                role_fit_score=90,
            )
            _insert_scan_reach_sources(conn)
            scan_reach = latest_scan_reach(conn)

            html_body = render_html(get_digest_rows(conn), [], scan_reach=scan_reach)
            text_body = render_text(get_digest_rows(conn), [], scan_reach=scan_reach)

            self.assertIn(
                "Scanned 1,247 postings across 2 companies this run",
                html_body,
            )
            self.assertIn(
                "Scanned 1,247 postings across 2 companies this run",
                text_body,
            )

    def test_html_digest_uses_email_safe_dark_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            add_text_intake(
                JOB_TEXT,
                db_path=db_path,
                source_url="https://example.com/template-check",
            )
            conn = _connect(db_path)
            _mark_non_fallback_evaluations(
                conn,
                recommendation="stretch",
                role_fit_score=90,
            )
            html_body = render_html(get_digest_rows(conn), [])
            text_body = render_text(get_digest_rows(conn), [])

            self.assertIn("LAYLINE · velocity made good", html_body)
            self.assertIn("Stretch / reach — calibration in progress, scrutinize", html_body)
            self.assertIn("Stretch / reach — calibration in progress, scrutinize", text_body)
            self.assertIn('role="presentation"', html_body)
            self.assertIn("max-width:600px", html_body)
            self.assertIn("font-family:Newsreader,Georgia", html_body)
            self.assertIn("font-family:'IBM Plex Sans',-apple-system", html_body)
            self.assertNotIn("<style", html_body.lower())
            td_tags = re.findall(r"<td\b[^>]*>", html_body)
            self.assertTrue(td_tags)
            self.assertTrue(
                all("background-color:" in tag or "bgcolor=" in tag for tag in td_tags)
            )


class FakeProvider:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        self.messages.append(message)
        return EmailSendResult(status="sent", provider_message_id="fake-message-id")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _insert_failed_source(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO companies (id, name, tier, enabled, warm_path, notes)
        VALUES (1, 'FailureCo', 1, 1, 0, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO job_sources (
          id, company_id, source_type, source_key, source_url, parser_version,
          health_status, expected_volume_min
        )
        VALUES (
          1, 1, 'greenhouse', 'failureco', 'https://example.com/jobs',
          'greenhouse_v1', 'failing', 10
        )
        """
    )
    record_source_run(
        conn,
        1,
        started_at="2026-06-24T10:00:00+00:00",
        finished_at="2026-06-24T10:01:00+00:00",
        status="failure",
        http_status=500,
        fetched_count=0,
        new_count=0,
        changed_count=0,
        error_summary="connector failed",
    )
    conn.commit()


def _insert_disabled_degraded_source(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO companies (id, name, tier, enabled, warm_path, notes)
        VALUES (2, 'DisabledCo', 1, 0, 0, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO job_sources (
          id, company_id, source_type, source_key, source_url, parser_version,
          health_status, expected_volume_min
        )
        VALUES (
          2, 2, 'lever', 'disabledco', 'https://example.com/jobs',
          'lever_v1', 'degraded', 10
        )
        """
    )
    conn.commit()


def _insert_scan_reach_sources(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO companies (id, name, tier, enabled, warm_path, notes)
        VALUES
          (10, 'ScanOne', 1, 1, 0, NULL),
          (11, 'ScanTwo', 1, 1, 0, NULL),
          (12, 'DisabledScan', 1, 0, 0, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO job_sources (
          id, company_id, source_type, source_key, source_url, parser_version,
          health_status, expected_volume_min
        )
        VALUES
          (10, 10, 'greenhouse', 'scanone', 'https://example.com/one',
           'greenhouse_v1', 'healthy', 10),
          (11, 11, 'ashby', 'scantwo', 'https://example.com/two',
           'ashby_v1', 'healthy', 10),
          (12, 12, 'lever', 'disabledscan', 'https://example.com/disabled',
           'lever_v1', 'healthy', 10)
        """
    )
    record_source_run(
        conn,
        10,
        started_at="2026-06-24T10:00:00+00:00",
        finished_at="2026-06-24T10:01:00+00:00",
        status="success",
        http_status=200,
        fetched_count=1000,
        new_count=0,
        changed_count=0,
        error_summary=None,
    )
    record_source_run(
        conn,
        11,
        started_at="2026-06-24T10:00:00+00:00",
        finished_at="2026-06-24T10:01:00+00:00",
        status="success",
        http_status=200,
        fetched_count=247,
        new_count=0,
        changed_count=0,
        error_summary=None,
    )
    record_source_run(
        conn,
        12,
        started_at="2026-06-24T10:00:00+00:00",
        finished_at="2026-06-24T10:01:00+00:00",
        status="success",
        http_status=200,
        fetched_count=9999,
        new_count=0,
        changed_count=0,
        error_summary=None,
    )
    conn.commit()


def _mark_non_fallback_evaluations(
    conn: sqlite3.Connection,
    *,
    title_contains: str | None = None,
    recommendation: str | None = None,
    role_fit_score: int | None = None,
    mark_non_fallback: bool = True,
) -> None:
    rows = conn.execute(
        """
        SELECT re.id, re.evaluation_json, jp.title
        FROM role_evaluations re
        JOIN job_postings jp ON jp.id = re.job_posting_id
        """
    ).fetchall()
    for row in rows:
        if title_contains is not None and title_contains not in row["title"]:
            continue
        payload = json.loads(row["evaluation_json"])
        if recommendation is not None:
            payload["recommendation"] = recommendation
        if role_fit_score is not None:
            payload["role_fit_score"] = role_fit_score
        if mark_non_fallback:
            payload.setdefault("provenance", {})
            payload["provenance"]["fallback_quality"] = "false"
            payload["provenance"]["model_version"] = "fake-claude"
            payload["provenance"]["evaluator_version"] = "hybrid_claude_v1"
        conn.execute(
            "UPDATE role_evaluations SET evaluation_json = ? WHERE id = ?",
            (json.dumps(payload), row["id"]),
        )
    conn.commit()


def _job_text(index: int) -> str:
    return f"""Company: CapCo {index:02d}
Title: Strategic Operations Manager {index:02d}
Location: Munich, Germany
Department: Strategy & Operations

Lead strategy and operations programs for cross-functional stakeholders.
Own executive rhythm, customer operations, transformation work, and program delivery.
"""


if __name__ == "__main__":
    unittest.main()
