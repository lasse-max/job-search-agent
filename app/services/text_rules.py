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
    "Cantonese": ("cantonese",),
    "Chinese": ("chinese",),
    "Korean": ("korean",),
    "Thai": ("thai",),
    "Vietnamese": ("vietnamese",),
    "Indonesian": ("indonesian", "bahasa indonesia"),
    "Malay": ("malay", "bahasa melayu"),
    "Greek": ("greek",),
    "Hungarian": ("hungarian",),
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

NON_LANGUAGE_FLUENCY_OBJECTS = {
    "communication",
    "data",
    "excel",
    "programming",
    "python",
    "sql",
    "statistics",
    "technology",
}

ISO_COMMON_LANGUAGE_NAMES = frozenset(
    name.casefold()
    for name in (
        "Abkhazian",
        "Afar",
        "Afrikaans",
        "Akan",
        "Albanian",
        "Amharic",
        "Arabic",
        "Aragonese",
        "Armenian",
        "Assamese",
        "Avaric",
        "Avestan",
        "Aymara",
        "Azerbaijani",
        "Bambara",
        "Bashkir",
        "Basque",
        "Belarusian",
        "Bengali",
        "Bislama",
        "Bosnian",
        "Breton",
        "Bulgarian",
        "Burmese",
        "Cantonese",
        "Catalan",
        "Chamorro",
        "Chechen",
        "Chichewa",
        "Chinese",
        "Church Slavonic",
        "Chuvash",
        "Cornish",
        "Corsican",
        "Cree",
        "Croatian",
        "Czech",
        "Danish",
        "Divehi",
        "Dutch",
        "Dzongkha",
        "English",
        "Esperanto",
        "Estonian",
        "Ewe",
        "Faroese",
        "Farsi",
        "Fijian",
        "Filipino",
        "Finnish",
        "Flemish",
        "French",
        "Fulah",
        "Gaelic",
        "Galician",
        "Ganda",
        "Georgian",
        "German",
        "Greek",
        "Greenlandic",
        "Guarani",
        "Gujarati",
        "Haitian",
        "Haitian Creole",
        "Hausa",
        "Hebrew",
        "Herero",
        "Hindi",
        "Hiri Motu",
        "Hungarian",
        "Icelandic",
        "Ido",
        "Igbo",
        "Indonesian",
        "Interlingua",
        "Interlingue",
        "Inuktitut",
        "Inupiaq",
        "Irish",
        "Italian",
        "Japanese",
        "Javanese",
        "Kalaallisut",
        "Kannada",
        "Kanuri",
        "Kashmiri",
        "Kazakh",
        "Khmer",
        "Kikuyu",
        "Kinyarwanda",
        "Kirghiz",
        "Komi",
        "Kongo",
        "Korean",
        "Kuanyama",
        "Kurdish",
        "Kyrgyz",
        "Lao",
        "Latin",
        "Latvian",
        "Limburgan",
        "Lingala",
        "Lithuanian",
        "Luba-Katanga",
        "Luxembourgish",
        "Macedonian",
        "Malagasy",
        "Malay",
        "Malayalam",
        "Maldivian",
        "Maltese",
        "Mandarin",
        "Manx",
        "Maori",
        "Marathi",
        "Marshallese",
        "Moldavian",
        "Moldovan",
        "Mongolian",
        "Nauru",
        "Navajo",
        "Ndonga",
        "Nepali",
        "Northern Sami",
        "Northern Sotho",
        "Norwegian",
        "Norwegian Bokmal",
        "Norwegian Nynorsk",
        "Nyanja",
        "Occitan",
        "Odia",
        "Ojibwa",
        "Oriya",
        "Oromo",
        "Ossetian",
        "Pali",
        "Panjabi",
        "Pashto",
        "Persian",
        "Polish",
        "Portuguese",
        "Punjabi",
        "Pushto",
        "Quechua",
        "Romanian",
        "Romansh",
        "Rundi",
        "Russian",
        "Samoan",
        "Sango",
        "Sanskrit",
        "Sardinian",
        "Scottish Gaelic",
        "Serbian",
        "Shona",
        "Sichuan Yi",
        "Sindhi",
        "Sinhala",
        "Sinhalese",
        "Slovak",
        "Slovenian",
        "Somali",
        "Southern Sotho",
        "Spanish",
        "Sundanese",
        "Swahili",
        "Swati",
        "Swedish",
        "Tagalog",
        "Tahitian",
        "Tajik",
        "Tamil",
        "Tatar",
        "Telugu",
        "Thai",
        "Tibetan",
        "Tigrinya",
        "Tonga",
        "Tsonga",
        "Tswana",
        "Turkish",
        "Turkmen",
        "Twi",
        "Uighur",
        "Ukrainian",
        "Urdu",
        "Uyghur",
        "Uzbek",
        "Valencian",
        "Venda",
        "Vietnamese",
        "Volapuk",
        "Walloon",
        "Welsh",
        "Western Frisian",
        "Wolof",
        "Xhosa",
        "Yiddish",
        "Yoruba",
        "Zhuang",
        "Zulu",
    )
)

KNOWN_LANGUAGE_MARKERS = {
    alias.casefold()
    for canonical, aliases in LANGUAGE_ALIASES.items()
    for alias in (canonical, *aliases)
} | ISO_COMMON_LANGUAGE_NAMES
KNOWN_LANGUAGE_PATTERN = re.compile(
    r"\b(?P<language>"
    + "|".join(
        r"\s+".join(re.escape(part) for part in marker.split())
        for marker in sorted(KNOWN_LANGUAGE_MARKERS, key=len, reverse=True)
    )
    + r")\b",
    flags=re.IGNORECASE,
)


def unsupported_language_requirement(
    text: str,
    profile_languages: dict[str, str],
) -> tuple[str, str] | None:
    """Return the first core required language outside the candidate profile."""

    supported_aliases = _supported_language_aliases(profile_languages)
    for fragment in _language_fragments(text, supported_aliases):
        generic = _generic_speaking_marker(fragment)
        if generic:
            language, parenthesized = generic
            if (
                not _language_is_supported(language, supported_aliases)
                and (
                    parenthesized
                    or not _matches_any(fragment, NICE_TO_HAVE_LANGUAGE_CONTEXT)
                )
            ):
                return language, fragment.strip()
        generic_required = _generic_hard_language_requirement(fragment)
        if (
            generic_required
            and not _language_is_supported(generic_required, supported_aliases)
        ):
            return generic_required, fragment.strip()
        for language, aliases in LANGUAGE_ALIASES.items():
            if any(alias in supported_aliases for alias in aliases):
                continue
            if any(
                re.search(pattern, fragment, flags=re.IGNORECASE)
                for alias in aliases
                for pattern in _hard_language_requirement_patterns(alias)
            ):
                return language, fragment.strip()
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
    for marker in KNOWN_LANGUAGE_MARKERS:
        language = _language_regex(marker)
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
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_location_variant_suffix(text: str, locations: list[str]) -> str:
    """Remove a trailing geography marker only when it is actually a location.

    Titles such as ``Strategist - London`` are location variants; titles such as
    ``Strategist - Customer Value`` are distinct roles and must remain separate.
    """

    cleaned = re.sub(r"\s+", " ", text).strip()
    match = re.match(
        r"^(?P<base>.+?)(?:\s+[-\u2013\u2014]\s+|\s*\()(?P<suffix>[^()]+?)\)?$",
        cleaned,
    )
    if not match:
        return cleaned
    suffix = match.group("suffix").strip()
    if not _is_location_suffix(suffix, locations):
        return cleaned
    return match.group("base").strip()


def _is_location_suffix(suffix: str, locations: list[str]) -> bool:
    normalized_suffix = _normal_words(suffix)
    if not normalized_suffix:
        return False
    known_region_suffixes = {
        "anz",
        "apac",
        "australia",
        "canada",
        "dach",
        "emea",
        "europe",
        "germany",
        "mena",
        "netherlands",
        "singapore",
        "spain",
        "sweden",
        "uk",
        "united kingdom",
        "us",
        "usa",
        "united states",
    }
    if normalized_suffix in known_region_suffixes:
        return True
    for location in locations:
        normalized_location = _normal_words(location)
        if not normalized_location:
            continue
        location_parts = {
            _normal_words(part)
            for part in re.split(r"[,/|]", location)
            if _normal_words(part)
        }
        if (
            normalized_suffix == normalized_location
            or normalized_suffix in location_parts
            or normalized_location.startswith(f"{normalized_suffix} ")
        ):
            return True
    return False


def _normal_words(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


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


def _language_fragments(
    text: str,
    supported_aliases: set[str],
) -> list[str]:
    fragments: list[str] = []
    for sentence in re.split(r"[\n.;•]+", text):
        sentence = _remove_satisfied_language_or_groups(
            sentence.strip(),
            supported_aliases,
        )
        if not sentence.strip():
            continue
        fragments.extend(
            fragment.strip()
            for fragment in sentence.split(",")
            if fragment.strip()
        )
    return fragments


def _remove_satisfied_language_or_groups(
    sentence: str,
    supported_aliases: set[str],
) -> str:
    """Remove only OR-connected language lists satisfied by a profile language."""

    mentions = [
        (
            match.start(),
            match.end(),
            re.sub(r"\s+", " ", match.group("language")).casefold(),
        )
        for match in KNOWN_LANGUAGE_PATTERN.finditer(sentence)
    ]
    if len(mentions) < 2:
        return sentence

    groups: list[list[tuple[int, int, str]]] = []
    current = [mentions[0]]
    for mention in mentions[1:]:
        prior = current[-1]
        between = sentence[prior[1] : mention[0]]
        if re.fullmatch(
            r"\s*(?:(?:,|and|or)\s*)+",
            between,
            flags=re.IGNORECASE,
        ):
            current.append(mention)
        else:
            groups.append(current)
            current = [mention]
    groups.append(current)

    removals: list[tuple[int, int]] = []
    for group in groups:
        if len(group) < 2:
            continue
        connectors = sentence[group[0][1] : group[-1][0]]
        if not re.search(r"\bor\b", connectors, flags=re.IGNORECASE):
            continue
        if any(
            _language_is_supported(marker, supported_aliases)
            for _, _, marker in group
        ):
            removals.append((group[0][0], group[-1][1]))

    for start, end in reversed(removals):
        sentence = f"{sentence[:start]} {sentence[end:]}"
    return sentence


def _language_requirement_patterns(alias: str) -> tuple[str, ...]:
    language = _language_regex(alias)
    return (
        rf"\b{language}[-\s]+speaking\b",
        rf"\bfluent\s+(?:in\s+)?{language}\b",
        rf"\bfluency\s+in\b.{{0,40}}\b{language}\b",
        rf"\bfluency\s+in\s+{language}\b.{{0,40}}\b(?:required|essential|mandatory)\b",
        rf"\bmust\s+be\s+fluent\s+in\s+{language}\b",
        rf"\b{language}\s+(?:fluency|required|mandatory)\b",
        rf"\b{language}\s+(?:is|are)\s+(?:required|essential|mandatory)\b",
        rf"\brequires?\s+{language}\b",
        rf"\b(?:native|near-native|professional|business|full professional)[-\s]+(?:level\s+)?{language}\b",
        rf"\b{language}\s+language\s+(?:skills?|proficiency)\b",
        rf"\bproficiency\s+in\s+{language}\b",
    )


def _hard_language_requirement_patterns(alias: str) -> tuple[str, ...]:
    language = _language_regex(alias)
    return (
        rf"\bfluency\s+in\s+{language}\b.{{0,40}}\b(?:required|essential|mandatory)\b",
        rf"\bmust\s+be\s+fluent\s+in\s+{language}\b",
        rf"\b{language}\s+(?:fluency\s+)?(?:is|are)\s+(?:required|essential|mandatory)\b",
        rf"\b{language}\s+(?:(?:is|are)\s+)?(?:required|essential|mandatory)\b",
        rf"\brequires?\s+(?:fluency\s+in\s+)?{language}\b",
    )


def _generic_speaking_marker(text: str) -> tuple[str, bool] | None:
    patterns = (
        (
            r"[\(\[]\s*(?P<language>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ -]{1,28})[-\s]+speaking\s*[\)\]]",
            True,
        ),
        (
            r"(?:^|[-–—,/])\s*(?P<language>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ -]{1,28})[-\s]+speaking\b",
            False,
        ),
    )
    for pattern, parenthesized in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            marker = re.sub(r"\s+", " ", match.group("language")).strip().casefold()
            for canonical, aliases in LANGUAGE_ALIASES.items():
                if marker == canonical.casefold() or marker in {
                    alias.casefold() for alias in aliases
                }:
                    return canonical, parenthesized
            if marker in KNOWN_LANGUAGE_MARKERS:
                return marker.title(), parenthesized
    return None


def _generic_hard_language_requirement(text: str) -> str | None:
    patterns = (
        r"\bfluency\s+in\s+(?P<language>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ-]{1,28})\s+"
        r"(?:is\s+)?(?:required|essential|mandatory)\b",
        r"\bmust\s+be\s+fluent\s+in\s+"
        r"(?P<language>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ-]{1,28})\b",
        r"\b(?P<language>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ-]{1,28})\s+fluency\s+"
        r"(?:is\s+)?(?:required|essential|mandatory)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        marker = match.group("language").casefold()
        if marker in NON_LANGUAGE_FLUENCY_OBJECTS:
            continue
        for canonical, aliases in LANGUAGE_ALIASES.items():
            if marker == canonical.casefold() or marker in {
                alias.casefold() for alias in aliases
            }:
                return canonical
        if marker in KNOWN_LANGUAGE_MARKERS:
            return marker.title()
    return None


def _language_is_supported(language: str, supported_aliases: set[str]) -> bool:
    aliases = LANGUAGE_ALIASES.get(language, (language.casefold(),))
    return any(alias.casefold() in supported_aliases for alias in aliases)


def _language_regex(alias: str) -> str:
    return r"\s+".join(re.escape(part) for part in alias.lower().split())


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
