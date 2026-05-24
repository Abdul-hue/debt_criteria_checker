
import pytest
from datetime import date, timedelta
from criteria_engine import _gambling_monthly

def _days_back(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()

def test_debug_gambling():
    tx_31 = {
        "description": "LADBROKES",
        "amount": "500.00",
        "transaction_date": _days_back(31),
    }
    tx_10 = {
        "description": "LADBROKES",
        "amount": "100.00",
        "transaction_date": _days_back(10),
    }

    print(f"\nToday: {date.today()}")
    print(f"31 days back: {_days_back(31)}")
    print(f"10 days back: {_days_back(10)}")

    result = _gambling_monthly([tx_31, tx_10])
    print(f"Result: {result}")
    assert result == 100.0
