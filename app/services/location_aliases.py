"""Conservative, config-driven district expansions for location-policy matching."""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata

from app.config import LocationAliasConfig, LocationPolicyConfig, load_location_policy


def resolve_location_aliases(
    locations: Iterable[str],
    policy: LocationPolicyConfig | None = None,
) -> list[str]:
    """Return search-only expansions without changing persisted/display locations.

    Each source location is resolved independently so one location's country cannot
    authorize another's ambiguous district. Unknown geographic context stays unknown.
    """
    policy = policy or load_location_policy()
    return [_resolve_location(location, policy.aliases) for location in locations]


def _resolve_location(location: str, aliases: tuple[LocationAliasConfig, ...]) -> str:
    text = _matching_text(location)
    for entry in aliases:
        patterns = [_literal_pattern(alias) for alias in sorted(entry.aliases, key=len, reverse=True)]
        if not any(re.search(pattern, text) for pattern in patterns):
            continue
        if entry.required_context_patterns and not any(
            re.search(pattern, text) for pattern in entry.required_context_patterns
        ):
            continue
        remainder = text
        for pattern in patterns:
            remainder = re.sub(pattern, " ", remainder)
        for pattern in entry.context_patterns:
            remainder = re.sub(pattern, " ", remainder)
        remainder = re.sub(r"\b(?:hybrid|remote|on[ -]?site|office)\b", " ", remainder)
        remainder = re.sub(r"\b\d{3,6}\b", " ", remainder)
        # Only punctuation/spacing may remain. Foreign country/state names are
        # not stripped, even when an expected country is also present.
        if re.search(r"\w", remainder):
            continue
        if re.search(_literal_pattern(entry.city), text):
            return location
        return f"{location} ({entry.city})"
    return location


def _literal_pattern(value: str) -> str:
    return rf"(?<!\w){re.escape(_matching_text(value))}(?!\w)"


def _matching_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().replace("\u00f8", "o"))
    return " ".join("".join(char for char in normalized if not unicodedata.combining(char)).split())
