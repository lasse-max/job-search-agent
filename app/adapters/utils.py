"""Shared adapter normalization helpers."""

from __future__ import annotations

import html
import re


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = TAG_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def compact_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()
