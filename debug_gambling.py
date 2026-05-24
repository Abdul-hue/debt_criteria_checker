
from datetime import date, timedelta
from debt_app.criteria_engine import _gambling_monthly

def _days_back(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()

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

print(f"Today: {date.today()}")
print(f"31 days back: {_days_back(31)}")
print(f"10 days back: {_days_back(10)}")

result = _gambling_monthly([tx_31, tx_10])
print(f"Result: {result}")
