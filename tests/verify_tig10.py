
import sys
import os
import django

# Add the project root to sys.path to import debt_app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'debt_app')))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.criteria_engine import _parse_case, _tig_10

def test_tig_10_missing_evidence_hard_block():
    print("Running test_tig_10_missing_evidence_hard_block...")
    payload = {
        "creditors": [
            {
                "creditor_name": "High Debt Bank",
                "balance": 1500.00,
                "linked_creditor": "REF-1"
            }
        ],
        "evidence_ledger": [
            {"ref": "REF-1", "is_verified": False}
        ]
    }
    c = _parse_case(payload)
    result = _tig_10(c)
    print(f"Result: {result.severity} - {result.message}")
    assert result.severity == "hard_block"
    assert "High Debt Bank" in result.message
    assert "£1,500.00" in result.message

def test_tig_10_missing_evidence_flag():
    print("Running test_tig_10_missing_evidence_flag...")
    payload = {
        "creditors": [
            {
                "creditor_name": "Low Debt Ltd",
                "balance": 500.00,
                "linked_creditor": "REF-2"
            }
        ],
        "evidence_ledger": [] # Empty ledger
    }
    c = _parse_case(payload)
    result = _tig_10(c)
    print(f"Result: {result.severity} - {result.message}")
    assert result.severity == "flag"
    assert "Low Debt Ltd" in result.message

def test_tig_10_all_verified_pass():
    print("Running test_tig_10_all_verified_pass...")
    payload = {
        "creditors": [
            {
                "creditor_name": "Verified Bank",
                "balance": 2000.00,
                "linked_creditor": "REF-OK"
            },
            {
                "creditor_name": "Small Verified",
                "balance": 100.00,
                "linked_creditor": "REF-SMALL"
            }
        ],
        "evidence_ledger": [
            {"ref": "REF-OK", "is_verified": True},
            {"ref": "REF-SMALL", "is_verified": True}
        ]
    }
    c = _parse_case(payload)
    result = _tig_10(c)
    print(f"Result: {result.severity} - {result.message}")
    assert result.severity == "pass"
    assert "2 creditors" in result.message

def test_tig_10_balance_zero_skipped():
    print("Running test_tig_10_balance_zero_skipped...")
    payload = {
        "creditors": [
            {
                "creditor_name": "Zero Balance",
                "balance": 0.00,
                "linked_creditor": "REF-NONE"
            }
        ],
        "evidence_ledger": []
    }
    c = _parse_case(payload)
    result = _tig_10(c)
    print(f"Result: {result.severity} - {result.message}")
    assert result.severity == "pass"
    assert "0 creditors" in result.message

if __name__ == "__main__":
    try:
        test_tig_10_missing_evidence_hard_block()
        test_tig_10_missing_evidence_flag()
        test_tig_10_all_verified_pass()
        test_tig_10_balance_zero_skipped()
        print("\nAll TIG-10 verification tests passed!")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        sys.exit(1)
