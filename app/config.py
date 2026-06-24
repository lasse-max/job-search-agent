"""Configuration helpers for the first vertical slice.

This module intentionally uses a tiny parser for the generated watchlist YAML so
the first slice can run before dependency installation. The parser is scoped to
the watchlist shape produced in Stage 0; later Stage 1 work can replace it with
PyYAML-backed validation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.models import CompanyConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_DB_PATH = DATA_DIR / "job_search_agent.sqlite"


@dataclass(frozen=True)
class RelevanceFilterConfig:
    version: str
    target_location_required: bool
    role_family_patterns: tuple[str, ...]


def _parse_scalar(value: str) -> object:
    value = value.strip()
    if value == "null":
        return None
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    if value.startswith('"') and value.endswith('"'):
        return ast.literal_eval(value)
    try:
        return int(value)
    except ValueError:
        return value


def load_watchlist(path: Path = CONFIG_DIR / "watchlist.yaml") -> list[dict[str, object]]:
    """Load company blocks from the generated Stage 0 watchlist file."""

    companies: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("  - name: "):
            if current is not None:
                companies.append(current)
            current = {"name": _parse_scalar(line.split(": ", 1)[1])}
            continue
        if current is None or not line.startswith("    ") or ": " not in line:
            continue
        key, value = line.strip().split(": ", 1)
        current[key] = _parse_scalar(value)

    if current is not None:
        companies.append(current)

    return companies


def load_company_config(company_name: str = "Databricks") -> CompanyConfig:
    """Return one enabled company config from the watchlist."""

    for company in load_watchlist():
        if company.get("name") == company_name:
            source_key = company.get("source_key")
            if not isinstance(source_key, str) or not source_key:
                raise ValueError(f"{company_name} does not have a configured source_key")
            return CompanyConfig(
                name=str(company["name"]),
                tier=int(company["tier"]),
                enabled=bool(company["enabled"]),
                ats_type=str(company["ats_type"]),
                source_key=source_key,
                careers_url=str(company["careers_url"]),
                target_locations=list(company.get("target_locations", [])),
                target_role_family_notes=str(company.get("target_role_family_notes", "")),
                warm_path=bool(company.get("warm_path", False)),
            )
    raise ValueError(f"Company not found in watchlist: {company_name}")


@lru_cache(maxsize=1)
def load_relevance_filter(
    path: Path = CONFIG_DIR / "relevance_filter.yaml",
) -> RelevanceFilterConfig:
    version = "relevance_filter_unknown"
    target_location_required = True
    role_family_patterns: list[str] = []
    active_list: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("version:"):
            version = str(_parse_scalar(stripped.split(":", 1)[1]))
            active_list = None
            continue
        if stripped.startswith("target_location_required:"):
            target_location_required = bool(_parse_scalar(stripped.split(":", 1)[1]))
            active_list = None
            continue
        if stripped == "role_family_patterns:":
            active_list = "role_family_patterns"
            continue
        if active_list == "role_family_patterns" and stripped.startswith("- "):
            role_family_patterns.append(str(_parse_scalar(stripped[2:])))

    if not role_family_patterns:
        raise ValueError(f"No role_family_patterns configured in {path}")

    return RelevanceFilterConfig(
        version=version,
        target_location_required=target_location_required,
        role_family_patterns=tuple(role_family_patterns),
    )
