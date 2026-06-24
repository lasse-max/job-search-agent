"""Manual URL/text intake source metadata."""

from __future__ import annotations


class ManualAdapter:
    """Metadata-only adapter for user-pasted or user-provided job descriptions."""

    source_type = "manual"
    parser_version = "manual_intake_v1"

    def endpoint(self, source_key: str) -> str:
        return f"manual://{source_key}"
