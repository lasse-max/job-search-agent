"""Validate a scheduled budget and reconcile owner-reported spend once per run."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re

import yaml


class BudgetSetupError(ValueError):
    """A launch cannot safely use this budget or reconciliation input."""


def _amount(value: object, *, positive: bool = False) -> float:
    try:
        amount = float(value) if not isinstance(value, bool) else float("nan")
    except (TypeError, ValueError):
        raise BudgetSetupError("Budget amounts must be finite nonnegative numbers.") from None
    if not math.isfinite(amount) or amount < 0 or (positive and amount == 0):
        raise BudgetSetupError("Budget amounts must be finite nonnegative; caps must be positive.")
    return amount


def monthly_cap(config_path: Path, today: date) -> float:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("month_overrides", {}), dict):
        raise BudgetSetupError("Invalid model budget configuration.")
    default = _amount(config.get("default_monthly_cap_usd"), positive=True)
    overrides = config.get("month_overrides", {})
    for month, cap in overrides.items():
        if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month):
            raise BudgetSetupError("Budget overrides must use a YYYY-MM UTC month.")
        _amount(cap, positive=True)
    return _amount(overrides.get(today.strftime("%Y-%m"), default), positive=True)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BudgetSetupError("Invalid cached budget state; reconcile before proceeding.")
    return data


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_budget(
    *, config_path: Path, ledger_path: Path, receipt_path: Path, today: date,
    run_id: str, run_attempt: int, full_backfill: bool,
    reconciled_mtd: str = "", reconciled_as_of: str = "",
) -> dict:
    cap = monthly_cap(config_path, today)
    if not run_id or run_attempt < 1:
        raise BudgetSetupError("A valid workflow run ID and attempt are required.")
    ledger = _read_json(ledger_path)
    for value in ledger.values():
        _amount(value)
    receipt = _read_json(receipt_path)
    month = today.strftime("%Y-%m")
    reconciled_mtd, reconciled_as_of = reconciled_mtd.strip(), reconciled_as_of.strip()
    supplied = bool(reconciled_mtd or reconciled_as_of)
    seeded = False
    if supplied:
        if not reconciled_mtd or reconciled_as_of != today.isoformat():
            raise BudgetSetupError("Supply MTD and today's exact YYYY-MM-DD UTC date together.")
        amount = _amount(reconciled_mtd)
        same_run = receipt.get("run_id") == run_id
        if run_attempt != 1 or same_run:
            if not same_run or receipt.get("amount_usd") != amount:
                raise BudgetSetupError("Rerun cannot replace spend; start a new reconciled dispatch.")
        else:
            # Replace the console month's value, never add the console total twice.
            ledger[month] = amount
            receipt = {
                "run_id": run_id, "initial_attempt": 1, "month": month,
                "as_of": reconciled_as_of, "amount_usd": amount,
            }
            seeded = True
    proof_is_current = bool(receipt) and (
        receipt.get("month") == month
        and receipt.get("as_of") == today.isoformat()
        and receipt.get("initial_attempt") == 1
        and bool(receipt.get("run_id"))
        and month in ledger
        and _amount(ledger[month]) >= _amount(receipt.get("amount_usd"))
    )
    if (full_backfill or supplied) and not proof_is_current:
        raise BudgetSetupError("Full backfill requires today's reconciled MTD and retained ledger proof.")
    if seeded:
        _write_json(ledger_path, ledger)
        _write_json(receipt_path, receipt)
    return {
        "monthly_cap_usd": cap, "month": month,
        "tracked_mtd_usd": _amount(ledger.get(month, 0)),
        "reconciled_today": proof_is_current, "replaced_ledger_value": seeded,
    }


def main() -> int:
    try:
        result = prepare_budget(
            config_path=Path("config/model_budget.yaml"),
            ledger_path=Path("data/model_spend_ledger.json"),
            receipt_path=Path("data/model_spend_reconciliation.json"),
            today=datetime.now(timezone.utc).date(),
            run_id=os.environ.get("GITHUB_RUN_ID", ""),
            run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
            full_backfill=os.environ.get("FULL_STALE_BACKFILL", "false").lower() == "true",
            reconciled_mtd=os.environ.get("RECONCILED_MTD_USD", ""),
            reconciled_as_of=os.environ.get("RECONCILED_AS_OF", ""),
        )
        output = Path(os.environ["GITHUB_OUTPUT"])
        with output.open("a", encoding="utf-8") as handle:
            handle.write(f"monthly_cap_usd={result['monthly_cap_usd']}\n")
    except BudgetSetupError as exc:
        print(f"::error title=Model budget not reconciled::{exc}")
        return 1
    except (OSError, ValueError, KeyError, yaml.YAMLError):
        print("::error title=Model budget setup failed::Check budget config and retained ledger state.")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
