"""One monotonic evaluation deadline shared by every source in a scan."""

from dataclasses import dataclass
import time
from typing import Callable

from app.config import load_recency_policy


@dataclass
class ScanBudget:
    deadline: float
    clock: Callable[[], float]
    stopped: bool = False
    evaluated_count: int = 0

    @classmethod
    def start(cls, *, clock: Callable[[], float] | None = None) -> "ScanBudget":
        clock = clock or time.monotonic
        minutes = load_recency_policy().backfill_wall_clock_budget_minutes
        return cls(deadline=clock() + minutes * 60, clock=clock)

    def expired(self) -> bool:
        self.stopped = self.stopped or self.clock() >= self.deadline
        return self.stopped


def budget_warning(evaluated: int, remaining: int) -> str:
    return (
        "backfill stopped at wall-clock budget: "
        f"{evaluated} evaluated, {remaining} remaining"
    )
