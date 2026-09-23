"""Separate candidate requirements/duties from company and legal boilerplate."""

from __future__ import annotations

import re


# Adapters flatten HTML, so recognize retained headings without relying on lines.
_HEADINGS = re.compile(
    r"\b(?:(?P<company>company description|company overview|about (?:us|the company)|"
    r"who we are)|"
    r"(?P<optional>preferred qualifications?|nice[- ]to[- ]haves?)|"
    r"(?P<required>minimum qualifications?|required qualifications?|"
    r"qualifications(?!\s+(?:of|for|to|in|at|under|within)\b)|"
    r"requirements(?!\s+(?:of|for|to|in|at|under|within)\b)|"
    r"what you(?:'ll| will)? (?:bring|need)|about you|who you are|"
    r"to be successful in this role you (?:have|will need))|"
    r"(?P<role>job description|(?:key )?responsibilities|what you(?:'ll| will) do|"
    r"about the role)|"
    r"(?P<legal>additional information|equal (?:employment )?opportunity(?: employer)?|"
    r"export control regulations|what we offer))\b\s*[:\-]?",
    flags=re.IGNORECASE,
)
_CANDIDATE = re.compile(
    r"\byou\b|\b(?:successful )?candidates?\b|\bapplicants?\b|"
    r"\bemployees?\b|\bemployment\b|"
    r"\b(?:this|the) (?:role|position)\b",
    flags=re.IGNORECASE,
)
_BOILERPLATE = re.compile(
    r"\b(?:do not|does not|without) discriminat\w*\b|"
    r"\b(?:legally )?protected (?:characteristics|status|classes)\b|"
    r"\b(?:military|veteran) (?:or veteran )?status\b|"
    r"\bexport control approval\b.{0,100}\bgovernment authorities\b",
    flags=re.IGNORECASE,
)
_COMPANY_PROSE = re.compile(
    r"^(?:(?:as (?:a|an|the) (?:company|employer),?\s+)?"
    r"we (?:serve|support|build|provide|develop|must|need to|are required to)|"
    r"our (?:company|platform|product|team)|the (?:company|platform|product))\b",
    flags=re.IGNORECASE,
)
CLEARANCE_PATTERN = (
    r"\b(?:security|sc|dv)\s+clearance\b|\bsecurity vetting\b|"
    r"\bsecurity check\s*\(sc\)|developed vetting|continuous (?:uk )?residency"
)
_DIRECT_DUTY = re.compile(
    r"\byou(?:'ll| will| must| are expected to| need to)\s+"
    r"(?:design|build|develop|write|ship|own|lead|deliver|deploy|support|serve)\b|"
    r"\bwe require (?:all )?(?:candidates|applicants) to\b|"
    r"\bemployment (?:is |will be )?contingent (?:on|upon)\b",
    flags=re.IGNORECASE,
)


def scoped_requirement_fragments(
    text: str, must_have_patterns: tuple[str, ...], requirement_patterns: tuple[str, ...] = (),
) -> list[str]:
    """Keep scoped requirements and headingless evidence, not employer prose.

    Qualification context persists across bullets; explicit candidate requirements
    can still be found in a legal/company section. Local negation/preferences are
    handled by the caller after this structural pass.
    """
    headings = []
    for heading in _HEADINGS.finditer(text):
        if heading.group("required") in {"requirements", "qualifications"}:
            # Lowercase inline nouns are not headings. Retain actual labels at
            # line/sentence boundaries or with a colon, including flattened JDs.
            before = text[:heading.start()].rstrip(" \t")
            if before and before[-1] not in "\n.!?;:" and ":" not in heading.group():
                continue
        headings.append(heading)
    sections = []
    start, kind = 0, "unknown"
    for heading in headings:
        sections.append((kind, text[start:heading.start()]))
        kind = heading.lastgroup or "unknown"
        start = heading.end()
    sections.append((kind, text[start:]))
    fragments = []
    for kind, section in sections:
        for sentence in re.split(r"[\n.;•]+", section):
            sentence = sentence.strip()
            if not sentence:
                continue
            prefix = {
                "required": "Requirements: ",
                "optional": "Preferred: ",
                "role": "Responsibilities: ",
            }.get(kind, "")
            employer_prose = _BOILERPLATE.search(sentence) or _COMPANY_PROSE.search(sentence)
            if kind not in {"company", "legal"} and not employer_prose:
                fragments.append(prefix + sentence)
                continue
            explicit_candidate = any(
                re.search(
                    pattern, sentence[subject.start():subject.end() + 140],
                    flags=re.IGNORECASE,
                )
                for subject in _CANDIDATE.finditer(sentence)
                for pattern in must_have_patterns
            ) or bool(_DIRECT_DUTY.search(sentence))
            bare_requirement = any(
                match.start() <= 12
                and has_nearby_requirement(sentence, match, must_have_patterns)
                for pattern in (*requirement_patterns, CLEARANCE_PATTERN)
                for match in re.finditer(pattern, sentence, flags=re.IGNORECASE)
            )
            if employer_prose and not explicit_candidate:
                continue
            if kind in {"company", "legal"} and not (explicit_candidate or bare_requirement):
                continue
            fragments.append(prefix + sentence)
    return fragments


def has_nearby_requirement(text: str, signal: re.Match[str], patterns: tuple[str, ...]) -> bool:
    """Do not borrow a 'must' from an unrelated part of a long JD fragment."""
    if text.startswith("Requirements: "):
        return True
    nearby = text[max(0, signal.start() - 100):signal.end() + 100]
    return any(re.search(pattern, nearby, flags=re.IGNORECASE) for pattern in patterns)
