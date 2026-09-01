import json

import pytest

from ad_service.core.budget import BudgetExceededError, BudgetLedger


def test_budget_persists_and_blocks_overspend(tmp_path) -> None:
    path = tmp_path / "budget.json"
    ledger = BudgetLedger(path, cap_usd=1.0)
    ledger.ensure_available(0.4)
    ledger.record(0.4)
    reloaded = BudgetLedger(path, cap_usd=1.0)
    assert reloaded.spent_usd == pytest.approx(0.4)
    with pytest.raises(BudgetExceededError):
        reloaded.ensure_available(0.61)
    assert json.loads(path.read_text())["spent_usd"] == 0.4
