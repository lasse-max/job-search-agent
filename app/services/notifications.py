"""Digest notification delivery through a swappable email provider."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.config import OUTPUT_DIR
from app.db import (
    has_delivered_payload,
    latest_delivered_notification_at,
    latest_source_failures,
    record_notification,
    get_digest_rows,
)
from app.services.digest import render_html, render_text


DEFAULT_RESEND_FROM = "Job Search Agent <onboarding@resend.dev>"


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str


@dataclass(frozen=True)
class EmailSendResult:
    status: str
    provider_message_id: str | None = None
    error_summary: str | None = None


class EmailProvider(Protocol):
    def send(self, message: EmailMessage) -> EmailSendResult:
        """Send one transactional email."""


@dataclass(frozen=True)
class ResendEmailProvider:
    api_key: str
    from_email: str = DEFAULT_RESEND_FROM
    timeout_seconds: int = 20

    def send(self, message: EmailMessage) -> EmailSendResult:
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self.from_email,
                    "to": [message.to],
                    "subject": message.subject,
                    "html": message.html_body,
                    "text": message.text_body,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return EmailSendResult(
                status="failed",
                error_summary=f"resend_send_failed: {type(exc).__name__}: {exc}",
            )

        message_id = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                raw_id = payload.get("id")
                message_id = str(raw_id) if raw_id else None
        except ValueError:
            message_id = None
        return EmailSendResult(status="sent", provider_message_id=message_id)


@dataclass(frozen=True)
class DigestDeliveryResult:
    status: str
    subject: str
    payload_hash: str
    role_count: int
    failure_count: int
    html_path: Path
    text_path: Path
    recipient: str
    error_summary: str | None = None


def deliver_digest(
    conn: sqlite3.Connection,
    *,
    output_dir: Path = OUTPUT_DIR,
    provider: EmailProvider | None = None,
    recipient: str | None = None,
    suppress_no_change: bool = True,
) -> DigestDeliveryResult:
    """Render and send the since-last digest, falling back to local files in dev."""

    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "latest_digest.html"
    text_path = output_dir / "latest_digest.txt"
    recipient = recipient or os.getenv("DIGEST_RECIPIENT_EMAIL") or ""
    since = latest_delivered_notification_at(conn)
    rows = get_digest_rows(conn, since=since)
    failures = latest_source_failures(conn)
    subject = _subject(len(rows), len(failures))
    payload_hash = _payload_hash(rows, failures)

    if suppress_no_change and not rows and not failures:
        record_notification(
            conn,
            notification_type="digest",
            payload_hash=payload_hash,
            status="suppressed_no_change",
            error_summary="No new or changed roles, and no source failures.",
        )
        conn.commit()
        return DigestDeliveryResult(
            status="suppressed_no_change",
            subject=subject,
            payload_hash=payload_hash,
            role_count=0,
            failure_count=0,
            html_path=html_path,
            text_path=text_path,
            recipient=recipient,
        )

    # Source failures are intentionally never suppressed, even if the payload repeats.
    if not failures and has_delivered_payload(conn, payload_hash):
        record_notification(
            conn,
            notification_type="digest",
            payload_hash=payload_hash,
            status="suppressed_duplicate",
            error_summary="Identical digest payload already delivered.",
        )
        conn.commit()
        return DigestDeliveryResult(
            status="suppressed_duplicate",
            subject=subject,
            payload_hash=payload_hash,
            role_count=len(rows),
            failure_count=0,
            html_path=html_path,
            text_path=text_path,
            recipient=recipient,
        )

    html_body = render_html(rows, failures)
    text_body = render_text(rows, failures)
    html_path.write_text(html_body, encoding="utf-8")
    text_path.write_text(text_body, encoding="utf-8")

    provider = provider or provider_from_env()
    if provider is not None and not recipient:
        error_summary = "DIGEST_RECIPIENT_EMAIL is required when email delivery is configured."
        record_notification(
            conn,
            notification_type="digest",
            payload_hash=payload_hash,
            status="failed",
            error_summary=error_summary,
        )
        conn.commit()
        return DigestDeliveryResult(
            status="failed",
            subject=subject,
            payload_hash=payload_hash,
            role_count=len(rows),
            failure_count=len(failures),
            html_path=html_path,
            text_path=text_path,
            recipient=recipient,
            error_summary=error_summary,
        )

    message = EmailMessage(
        to=recipient,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )
    if provider is None:
        record_notification(
            conn,
            notification_type="digest",
            payload_hash=payload_hash,
            status="fallback",
            error_summary=f"No email API key configured; wrote {html_path}.",
        )
        conn.commit()
        return DigestDeliveryResult(
            status="fallback",
            subject=subject,
            payload_hash=payload_hash,
            role_count=len(rows),
            failure_count=len(failures),
            html_path=html_path,
            text_path=text_path,
            recipient=recipient,
            error_summary="No email API key configured; local HTML fallback used.",
        )

    sent = provider.send(message)
    record_notification(
        conn,
        notification_type="digest",
        payload_hash=payload_hash,
        status=sent.status,
        error_summary=sent.error_summary,
    )
    conn.commit()
    return DigestDeliveryResult(
        status=sent.status,
        subject=subject,
        payload_hash=payload_hash,
        role_count=len(rows),
        failure_count=len(failures),
        html_path=html_path,
        text_path=text_path,
        recipient=recipient,
        error_summary=sent.error_summary,
    )


def provider_from_env() -> EmailProvider | None:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return None
    return ResendEmailProvider(
        api_key=api_key,
        from_email=os.getenv("DIGEST_FROM_EMAIL") or DEFAULT_RESEND_FROM,
    )


def _subject(role_count: int, failure_count: int) -> str:
    if role_count == 0 and failure_count == 0:
        return "Job Search Digest: no new roles"
    parts = [f"{role_count} new/changed role{'s' if role_count != 1 else ''}"]
    if failure_count:
        parts.append(f"{failure_count} source issue{'s' if failure_count != 1 else ''}")
    return "Job Search Digest: " + ", ".join(parts)


def _payload_hash(rows: list[sqlite3.Row], failures: list[sqlite3.Row]) -> str:
    payload = {
        "roles": [
            {
                "job_id": row["job_id"],
                "source_type": row["source_type"],
                "source_key": row["source_key"],
                "source_job_id": row["source_job_id"],
                "evaluated_at": row["evaluated_at"],
                "evaluation_json": json.loads(row["evaluation_json"]),
            }
            for row in rows
        ],
        "failures": [
            {
                "company": row["company"],
                "source_type": row["source_type"],
                "source_key": row["source_key"],
                "health_status": row["health_status"],
                "status": row["status"],
                "error_summary": row["error_summary"],
                "finished_at": row["finished_at"],
            }
            for row in failures
        ],
        "schema": "digest_payload_v1",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
