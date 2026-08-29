"""
Regression test for the Valid8IP-style Experian "bureau search" credit
report layout (see integrations/credit_report.py module docstring for
_split_valid8_accounts / _parse_valid8_account).

Before this fix, a report in this layout matched zero blocks in
_split_experian_accounts() (its "{Creditor} - {Category}" header never
occurs in this format) and silently extracted 0 accounts from a real
28-account report — reported as "success" with accounts_found=0, the
exact failure mode flagged in CreditReportUploadView.

The fixture PDF path below is developer-machine-specific (the sample the
bug was diagnosed against) — the test skips gracefully if it isn't present
rather than failing CI on a missing local file.
"""
import os

import pytest

from debt_app.integrations.credit_report import extract_credit_report

SAMPLE_PDF = r"C:\Users\Canton Computers\Desktop\janice-doyle-credit-search.pdf"


@pytest.mark.skipif(not os.path.exists(SAMPLE_PDF), reason="sample PDF not present on this machine")
class TestValid8CreditSearchFormat:
    def test_extracts_all_accounts(self):
        result = extract_credit_report(SAMPLE_PDF)
        assert "extraction_error" not in result
        assert result["agency"] == "Experian"
        # The report's own Summary section states "Number: 28" CAIS records.
        assert len(result["accounts"]) == 28

    def test_total_balance_matches_report_summary(self):
        # The report's own Summary section states "Total Balance: £5,020.00" —
        # an independent check baked into the source document itself, not
        # something this test derives from the extractor's own output.
        result = extract_credit_report(SAMPLE_PDF)
        total_pence = sum(a["current_balance"] or 0 for a in result["accounts"])
        assert total_pence == 502000

    def test_default_status_account_has_default_balance(self):
        result = extract_credit_report(SAMPLE_PDF)
        capital_one = [
            a for a in result["accounts"]
            if a["raw_name"] == "CAPITAL ONE" and a["account_status"] == "Default"
        ]
        assert len(capital_one) == 3
        for acct in capital_one:
            assert acct["worst_status"] == "Default"
            assert acct["current_balance"] is not None

    def test_no_false_positive_accounts_from_other_sections(self):
        # The Voters Roll section contains "Main Applicant - Current Address"
        # / "Undisclosed - Undisclosed Address" style lines that the generic
        # Experian header fallback regex can mistake for account headers —
        # the Valid8 path (anchored on "Company:") must never surface these.
        result = extract_credit_report(SAMPLE_PDF)
        names = {a["raw_name"] for a in result["accounts"]}
        assert "Main Applicant" not in names
        assert "Undisclosed" not in names
