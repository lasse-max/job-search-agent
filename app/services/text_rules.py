"""Shared text rules for evaluator gating and posting normalization."""

from __future__ import annotations

import re


LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "English": ("english",),
    "German": ("german", "deutsch"),
    "French": ("french", "français", "francais"),
    "Spanish": ("spanish", "español", "espanol"),
    "Italian": ("italian", "italiano"),
    "Japanese": ("japanese",),
    "Dutch": ("dutch",),
    "Portuguese": ("portuguese",),
    "Swedish": ("swedish",),
    "Danish": ("danish",),
    "Norwegian": ("norwegian",),
    "Finnish": ("finnish",),
    "Polish": ("polish",),
    "Czech": ("czech",),
    "Slovak": ("slovak",),
    "Romanian": ("romanian",),
    "Turkish": ("turkish",),
    "Arabic": ("arabic",),
    "Hebrew": ("hebrew",),
    "Mandarin": ("mandarin",),
    "Chinese": ("chinese",),
    "Korean": ("korean",),
}

NICE_TO_HAVE_LANGUAGE_CONTEXT = (
    r"\bpreferred\b",
    r"\bnice to have\b",
    r"\ba plus\b",
    r"\bbonus\b",
    r"\basset\b",
    r"\bnot required\b",
    r"\boptional\b",
    r"\bhelpful\b",
    r"\bdesirable\b",
)


def unsupported_language_requirement(
    text: str,
    profile_languages: dict[str, str],
) -> tuple[str, str] | None:
    """Return the first core required language outside the candidate profile."""

    supported_aliases = _supported_language_aliases(profile_languages)
    for fragment in _language_fragments(text):
        if _matches_any(fragment, NICE_TO_HAVE_LANGUAGE_CONTEXT):
            continue
        for language, aliases in LANGUAGE_ALIASES.items():
            if any(alias in supported_aliases for alias in aliases):
                continue
            if any(
                re.search(pattern, fragment, flags=re.IGNORECASE)
                for alias in aliases
                for pattern in _language_requirement_patterns(alias)
            ):
                return language, fragment.strip()
    return None


def strip_language_variant_markers(text: str) -> str:
    """Remove language-specific role markers while preserving the base role title."""

    cleaned = text
    for aliases in LANGUAGE_ALIASES.values():
        for alias in aliases:
            language = _language_regex(alias)
            cleaned = re.sub(
                rf"\s*[\(\[\{{]\s*{language}[-\s]+speaking\s*[\)\]\}}]\s*",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(
                rf"\s*[-–—,/]\s*{language}[-\s]+speaking\b",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(
                rf"\b{language}[-\s]+speaking\s*[-–—,/]\s*",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
    return re.sub(r"\s+", " ", cleaned).strip()


def _supported_language_aliases(profile_languages: dict[str, str]) -> set[str]:
    supported: set[str] = set()
    for language, proficiency in profile_languages.items():
        if not _is_profile_language_strength_usable(proficiency):
            continue
        normalized = language.lower().strip()
        supported.add(normalized)
        for canonical, aliases in LANGUAGE_ALIASES.items():
            if normalized == canonical.lower() or normalized in aliases:
                supported.update(aliases)
    return supported


def _is_profile_language_strength_usable(proficiency: str) -> bool:
    normalized = proficiency.lower()
    return any(term in normalized for term in ("native", "professional", "fluent"))


def _language_fragments(text: str) -> list[str]:
    return [
        fragment.strip()
        for fragment in re.split(r"[\n.;•]+", text)
        if fragment.strip()
    ]


def _language_requirement_patterns(alias: str) -> tuple[str, ...]:
    language = _language_regex(alias)
    return (
        rf"\b{language}[-\s]+speaking\b",
        rf"\bfluent\s+(?:in\s+)?{language}\b",
        rf"\bfluency\s+in\b.{{0,40}}\b{language}\b",
        rf"\b{language}\s+(?:fluency|required|mandatory)\b",
        rf"\brequires?\s+{language}\b",
        rf"\b(?:native|near-native|professional|business|full professional)[-\s]+(?:level\s+)?{language}\b",
        rf"\b{language}\s+language\s+(?:skills?|proficiency)\b",
        rf"\bproficiency\s+in\s+{language}\b",
    )


def _language_regex(alias: str) -> str:
    return r"\s+".join(re.escape(part) for part in alias.lower().split())


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
