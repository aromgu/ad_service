from __future__ import annotations

import json
from pathlib import Path


class BudgetExceededError(RuntimeError):
    pass


class BudgetLedger:
    def __init__(self, path: Path, cap_usd: float = 10.0) -> None:
        if cap_usd <= 0:
            raise ValueError("budget cap must be positive")
        self.path = path
        self.cap_usd = cap_usd
        self.spent_usd = 0.0
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.spent_usd = float(payload.get("spent_usd", 0.0))

    def ensure_available(self, estimated_cost_usd: float) -> None:
        if self.spent_usd + estimated_cost_usd > self.cap_usd:
            raise BudgetExceededError(
                f"budget cap ${self.cap_usd:.2f} would be exceeded "
                f"(${self.spent_usd:.4f} spent + ${estimated_cost_usd:.4f} estimated)"
            )

    def record(self, cost_usd: float) -> None:
        self.spent_usd += max(0.0, cost_usd)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"cap_usd": self.cap_usd, "spent_usd": round(self.spent_usd, 6)},
                indent=2,
            ),
            encoding="utf-8",
        )
