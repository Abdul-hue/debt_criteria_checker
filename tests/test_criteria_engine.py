"""
Unit tests for criteria_engine.py

Covers every rule that has a threshold — tests at, below, and above the threshold.
Also covers WATCH/TIX/EVOLVE guard logic (rules must not fire when representative absent).

Run with:
    python -m pytest tests/test_criteria_engine.py -v
"""

import pytest
from datetime import date, timedelta
from criteria_engine import (
    assess_case,
    _parse_case,
    _tig_01, _tig_02, _tig_11, _tig_18, _tig_19_1, _tig_20, _tig_20_1,
    _tig_21_2,
    _watch_22_2, _watch_22_5, _watch_22_8, _watch_22_9, _watch_22_10,
    _tix_04,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()

def _days_back(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()

def _base_payload(**overrides) -> dict:
    """Minimal valid payload that passes TIG-01 and TIG-02."""
    payload = {
        "applicationId": "test-001",
        "clientInfo": {"dateOfBirth": "1980-01-01"},
        "creditors": [
            {"creditor_name": "Barclays", "balance": "4000.00", "creditor_type": "unsecured_loan"},
            {"creditor_name": "HSBC",    "balance": "3000.00", "creditor_type": "unsecured_loan"},
        ],
        "gold_transactions": [],
        "mortgage_details": [],
        "financial_summary": {
            "total_income": 2500.00,
            "total_expenditure": 1800.00,
            "net_balance": 700.00,
            "income_source": "payslip",
            "documents": {},
        },
        "evidence_ledger": [],
        "documents": [
            {
                "document_type": "bank_statement",
                "is_valid": True,
                "extracted_data": {
                    "account_holder": "John Doe",
                    "statement_date": _today(),
                },
            },
            {
                "document_type": "payslip",
                "is_valid": True,
                "extracted_data": {"statement_date": _today()},
            },
        ],
        "crm_data": {
            "total_unsecured_debt": 7000.00,
            "total_secured_debt": 0.00,
        },
        "has_property": False,
        "has_vehicle": False,
        "has_mortgage": False,
        "has_job": True,
        "has_uc_journal": False,
    }
    payload.update(overrides)
    return payload


def _parsed(**overrides):
    return _parse_case(_base_payload(**overrides))


# ---------------------------------------------------------------------------
# TIG-01 — minimum debt £6,000
# ---------------------------------------------------------------------------

class TestTIG01:
    def test_below_threshold_blocks(self):
        c = _parsed(crm_data={"total_unsecured_debt": 5999.99})
        r = _tig_01(c)
        assert r.severity == "hard_block"
        assert r.triggered is True
        assert r.actual_value == pytest.approx(5999.99)

    def test_at_threshold_passes(self):
        c = _parsed(crm_data={"total_unsecured_debt": 6000.00})
        r = _tig_01(c)
        assert r.severity == "pass"
        assert r.triggered is False

    def test_above_threshold_passes(self):
        c = _parsed(crm_data={"total_unsecured_debt": 6001.00})
        r = _tig_01(c)
        assert r.severity == "pass"

    def test_threshold_and_actual_populated(self):
        c = _parsed(crm_data={"total_unsecured_debt": 4000.00})
        r = _tig_01(c)
        assert r.threshold == pytest.approx(6000.0)
        assert r.actual_value == pytest.approx(4000.0)


# ---------------------------------------------------------------------------
# TIG-02 — minimum disposable income > £100
# ---------------------------------------------------------------------------

class TestTIG02:
    def test_at_threshold_blocks(self):
        """<= 100 should block — boundary is exclusive."""
        payload = _base_payload()
        payload["financial_summary"]["net_balance"] = 100.00
        c = _parse_case(payload)
        r = _tig_02(c)
        assert r.severity == "hard_block"

    def test_below_threshold_blocks(self):
        payload = _base_payload()
        payload["financial_summary"]["net_balance"] = 99.00
        c = _parse_case(payload)
        r = _tig_02(c)
        assert r.severity == "hard_block"

    def test_above_threshold_passes(self):
        payload = _base_payload()
        payload["financial_summary"]["net_balance"] = 101.00
        c = _parse_case(payload)
        r = _tig_02(c)
        assert r.severity == "pass"

    def test_zero_di_blocks(self):
        payload = _base_payload()
        payload["financial_summary"]["net_balance"] = 0.00
        c = _parse_case(payload)
        r = _tig_02(c)
        assert r.severity == "hard_block"


# ---------------------------------------------------------------------------
# TIG-11 — bank statement + gambling thresholds
# ---------------------------------------------------------------------------

class TestTIG11:
    def _make_gambling_tx(self, amount: float) -> dict:
        return {
            "description": "LADBROKES",
            "amount": str(amount),
            "transaction_type": "money_out",
            "signed_amount": -amount,
            "transaction_date": _today(),
        }

    def test_no_bank_statement_blocks(self):
        payload = _base_payload()
        payload["documents"] = []  # remove all docs
        c = _parse_case(payload)
        r = _tig_11(c)
        assert r.severity == "hard_block"
        assert "No valid bank statement" in r.message

    def test_old_bank_statement_blocks(self):
        payload = _base_payload()
        payload["documents"] = [{
            "document_type": "bank_statement",
            "is_valid": True,
            "extracted_data": {
                "account_holder": "John Doe",
                "statement_date": _days_back(91),
            },
        }]
        c = _parse_case(payload)
        r = _tig_11(c)
        assert r.severity == "hard_block"
        assert "older than 90 days" in r.message

    def test_missing_account_holder_blocks(self):
        payload = _base_payload()
        payload["documents"] = [{
            "document_type": "bank_statement",
            "is_valid": True,
            "extracted_data": {
                "account_holder": "",
                "statement_date": _today(),
            },
        }]
        c = _parse_case(payload)
        r = _tig_11(c)
        assert r.severity == "hard_block"
        assert "account_holder" in r.message

    def test_gambling_201_flags(self):
        payload = _base_payload()
        payload["gold_transactions"] = [self._make_gambling_tx(201.00)]
        c = _parse_case(payload)
        r = _tig_11(c)
        assert r.severity == "flag"
        assert r.actual_value == pytest.approx(201.0)

    def test_gambling_200_passes(self):
        payload = _base_payload()
        payload["gold_transactions"] = [self._make_gambling_tx(200.00)]
        c = _parse_case(payload)
        r = _tig_11(c)
        # 200 is not > 200, so should not flag on gambling
        assert r.severity == "pass"

    def test_gambling_1001_hard_blocks(self):
        payload = _base_payload()
        payload["gold_transactions"] = [self._make_gambling_tx(1001.00)]
        c = _parse_case(payload)
        r = _tig_11(c)
        assert r.severity == "hard_block"
        assert r.actual_value == pytest.approx(1001.0)

    def test_gambling_1000_flags_not_blocks(self):
        """£1,000 exactly is > 200 but not > 1000, so should flag."""
        payload = _base_payload()
        payload["gold_transactions"] = [self._make_gambling_tx(1000.00)]
        c = _parse_case(payload)
        r = _tig_11(c)
        assert r.severity == "flag"


# ---------------------------------------------------------------------------
# TIG-18 — recent spending >= monthly income
# ---------------------------------------------------------------------------

class TestTIG18:
    def _tx(self, amount: float) -> dict:
        return {
            "description": "PURCHASE",
            "amount": str(amount),
            "transaction_type": "money_out",
            "signed_amount": -amount,
            "transaction_date": _days_back(10),
        }

    def test_spend_equals_income_flags(self):
        payload = _base_payload()
        payload["financial_summary"]["total_income"] = 1000.00
        payload["gold_transactions"] = [self._tx(1000.00)]
        c = _parse_case(payload)
        from criteria_engine import _tig_18
        r = _tig_18(c)
        assert r.severity == "flag"

    def test_spend_below_income_passes(self):
        payload = _base_payload()
        payload["financial_summary"]["total_income"] = 1000.00
        payload["gold_transactions"] = [self._tx(999.00)]
        c = _parse_case(payload)
        from criteria_engine import _tig_18
        r = _tig_18(c)
        assert r.severity == "pass"


# ---------------------------------------------------------------------------
# TIG-19 vs TIG-20 vs TIG-20.1 — severity separation
# ---------------------------------------------------------------------------

class TestShopDirectCreation:
    def _sd_tx(self) -> dict:
        return {
            "description": "VERY CATALOGUE",
            "amount": "50.00",
            "transaction_type": "money_out",
            "signed_amount": -50.0,
            "transaction_date": _days_back(10),
        }

    def _creation_tx(self) -> dict:
        return {
            "description": "CREATION FINANCE",
            "amount": "100.00",
            "transaction_type": "money_out",
            "signed_amount": -100.0,
            "transaction_date": _days_back(10),
        }

    def test_tig_19_is_flag_not_hard_block(self):
        payload = _base_payload()
        payload["gold_transactions"] = [self._sd_tx()]
        c = _parse_case(payload)
        from criteria_engine import _tig_19
        r = _tig_19(c)
        assert r.severity == "flag"
        assert r.rule_id == "TIG-19"

    def test_tig_20_is_flag_not_hard_block(self):
        payload = _base_payload()
        payload["gold_transactions"] = [self._creation_tx()]
        # Remove Creation from creditors so TIG-20.1 creditor check doesn't fire
        payload["creditors"] = [
            {"creditor_name": "Barclays", "balance": "4000.00", "creditor_type": "unsecured_loan"},
        ]
        c = _parse_case(payload)
        r = _tig_20(c)
        assert r.severity == "flag"
        assert r.rule_id == "TIG-20"

    def test_tig_20_1_is_hard_block(self):
        payload = _base_payload()
        payload["gold_transactions"] = [self._creation_tx()]
        c = _parse_case(payload)
        r = _tig_20_1(c)
        assert r.severity == "hard_block"
        assert r.rule_id == "TIG-20.1"

    def test_tig_19_1_hard_block_on_young_account(self):
        payload = _base_payload()
        payload["creditors"] = [
            {"creditor_name": "Very", "balance": "1000.00",
             "creditor_type": "catalogue", "account_age_months": 3},
            {"creditor_name": "HSBC", "balance": "5000.00", "creditor_type": "unsecured_loan"},
        ]
        c = _parse_case(payload)
        r = _tig_19_1(c)
        assert r.severity == "hard_block"
        assert r.actual_value == pytest.approx(3.0)
        assert r.threshold == pytest.approx(6.0)

    def test_tig_19_1_passes_at_6_months(self):
        payload = _base_payload()
        payload["creditors"] = [
            {"creditor_name": "Very", "balance": "1000.00",
             "creditor_type": "catalogue", "account_age_months": 6},
        ]
        c = _parse_case(payload)
        r = _tig_19_1(c)
        assert r.severity == "pass"


# ---------------------------------------------------------------------------
# TIG-21.2 — Link Financial minimum debt
# ---------------------------------------------------------------------------

class TestTIG212:
    def _link_payload(self, total_debt: float) -> dict:
        return _base_payload(crm_data={"total_unsecured_debt": total_debt}, creditors=[
            {"creditor_name": "Link Financial", "balance": str(total_debt * 0.6), "creditor_type": "unsecured_loan"},
            {"creditor_name": "Barclays",       "balance": str(total_debt * 0.4), "creditor_type": "unsecured_loan"},
        ])

    def test_below_12000_blocks(self):
        c = _parse_case(self._link_payload(11999.00))
        r = _tig_21_2(c)
        assert r.severity == "hard_block"

    def test_at_12000_passes(self):
        c = _parse_case(self._link_payload(12000.00))
        r = _tig_21_2(c)
        assert r.severity == "pass"

    def test_above_12000_passes(self):
        c = _parse_case(self._link_payload(15000.00))
        r = _tig_21_2(c)
        assert r.severity == "pass"


# ---------------------------------------------------------------------------
# WATCH-22.2 — months to repay threshold 72
# ---------------------------------------------------------------------------

class TestWATCH222:
    """months_to_repay = total_debt / disposable_income; <= 72 -> hard_block."""

    def _case(self, total_debt: float, di: float) -> dict:
        payload = _base_payload()
        payload["crm_data"] = {"total_unsecured_debt": total_debt}
        payload["financial_summary"]["net_balance"] = di
        return _parse_case(payload)

    def test_exactly_72_months_blocks(self):
        # debt=7200, di=100 -> 72.0 months
        c = self._case(7200.0, 100.0)
        r = _watch_22_2(c)
        assert r.severity == "hard_block"
        assert r.actual_value == pytest.approx(72.0)

    def test_71_months_blocks(self):
        c = self._case(7100.0, 100.0)
        r = _watch_22_2(c)
        assert r.severity == "hard_block"

    def test_73_months_passes(self):
        c = self._case(7300.0, 100.0)
        r = _watch_22_2(c)
        assert r.severity == "pass"

    def test_threshold_value_is_72(self):
        c = self._case(7200.0, 100.0)
        r = _watch_22_2(c)
        assert r.threshold == pytest.approx(72.0)


# ---------------------------------------------------------------------------
# WATCH-22.5 — single creditor hard block (NOT flag)
# ---------------------------------------------------------------------------

class TestWATCH225:
    def test_one_creditor_hard_blocks(self):
        payload = _base_payload()
        payload["creditors"] = [
            {"creditor_name": "Barclays", "balance": "7000.00", "creditor_type": "unsecured_loan"},
        ]
        c = _parse_case(payload)
        r = _watch_22_5(c)
        assert r.severity == "hard_block"
        assert r.triggered is True

    def test_second_creditor_under_500_hard_blocks(self):
        payload = _base_payload()
        payload["creditors"] = [
            {"creditor_name": "Barclays", "balance": "6500.00", "creditor_type": "unsecured_loan"},
            {"creditor_name": "HSBC",    "balance": "499.00",  "creditor_type": "unsecured_loan"},
        ]
        c = _parse_case(payload)
        r = _watch_22_5(c)
        assert r.severity == "hard_block"

    def test_two_qualifying_creditors_passes(self):
        payload = _base_payload()
        payload["creditors"] = [
            {"creditor_name": "Barclays", "balance": "4000.00", "creditor_type": "unsecured_loan"},
            {"creditor_name": "HSBC",    "balance": "3000.00", "creditor_type": "unsecured_loan"},
        ]
        c = _parse_case(payload)
        r = _watch_22_5(c)
        assert r.severity == "pass"

    def test_severity_is_hard_block_not_flag(self):
        """Confirmed bug fix: was 'flag' in original seed, must be 'hard_block'."""
        payload = _base_payload()
        payload["creditors"] = [
            {"creditor_name": "Barclays", "balance": "7000.00", "creditor_type": "unsecured_loan"},
        ]
        c = _parse_case(payload)
        r = _watch_22_5(c)
        assert r.severity == "hard_block", "WATCH-22.5 must be hard_block not flag"


# ---------------------------------------------------------------------------
# WATCH-22.8 — client age 80+ is INFO not block
# ---------------------------------------------------------------------------

class TestWATCH228:
    def test_age_80_is_info(self):
        payload = _base_payload()
        # Set DOB to make age exactly 80
        dob = (date.today() - timedelta(days=80 * 365)).isoformat()
        payload["clientInfo"]["dateOfBirth"] = dob
        c = _parse_case(payload)
        r = _watch_22_8(c)
        assert r.severity == "info"
        assert r.triggered is False  # info rules do not "trigger" a block

    def test_age_79_passes(self):
        dob = (date.today() - timedelta(days=79 * 365)).isoformat()
        payload = _base_payload()
        payload["clientInfo"]["dateOfBirth"] = dob
        c = _parse_case(payload)
        r = _watch_22_8(c)
        assert r.severity == "pass"


# ---------------------------------------------------------------------------
# WATCH-22.9 vs WATCH-22.10 — vehicle thresholds
# ---------------------------------------------------------------------------

class TestVehicleThresholds:
    def test_watch_22_9_at_threshold_passes(self):
        payload = _base_payload(vehicle_value=9000.0)
        c = _parse_case(payload)
        r = _watch_22_9(c)
        assert r.severity == "pass"

    def test_watch_22_9_above_threshold_flags(self):
        payload = _base_payload(vehicle_value=9001.0)
        c = _parse_case(payload)
        r = _watch_22_9(c)
        assert r.severity == "flag"
        assert r.threshold == pytest.approx(9000.0)

    def test_watch_22_10_threshold_is_400(self):
        """WATCH HP threshold must be 400."""
        payload = _base_payload()
        payload["gold_transactions"] = [{
            "description": "CAR FINANCE HP",
            "amount": "401.00",
            "transaction_type": "money_out",
            "signed_amount": -401.0,
            "transaction_date": _today(),
        }]
        c = _parse_case(payload)
        r = _watch_22_10(c)
        assert r.severity == "flag"
        assert r.threshold == pytest.approx(400.0)

    def test_watch_22_10_at_threshold_passes(self):
        payload = _base_payload()
        payload["gold_transactions"] = [{
            "description": "CAR FINANCE HP",
            "amount": "400.00",
            "transaction_type": "money_out",
            "signed_amount": -400.0,
            "transaction_date": _today(),
        }]
        c = _parse_case(payload)
        r = _watch_22_10(c)
        assert r.severity == "pass"


# ---------------------------------------------------------------------------
# TIX-04 — HP threshold is 250, NOT 400
# ---------------------------------------------------------------------------

class TestTIX04:
    def _hp_payload(self, amount: float) -> dict:
        payload = _base_payload()
        payload["gold_transactions"] = [{
            "description": "CAR FINANCE HP",
            "amount": str(amount),
            "transaction_type": "money_out",
            "signed_amount": -amount,
            "transaction_date": _today(),
        }]
        return payload

    def test_threshold_is_250_not_400(self):
        """Key requirement: TIX threshold is 250, WATCH is 400. They must be different."""
        c = _parse_case(self._hp_payload(251.0))
        r = _tix_04(c)
        assert r.severity == "flag"
        assert r.threshold == pytest.approx(250.0), "TIX-04 threshold must be 250, not 400"

    def test_at_250_passes(self):
        c = _parse_case(self._hp_payload(250.0))
        r = _tix_04(c)
        assert r.severity == "pass"

    def test_300_flags_for_tix_but_watch_would_pass(self):
        """HP=300 triggers TIX-04 (>250) but not WATCH-22.10 (>400)."""
        c = _parse_case(self._hp_payload(300.0))
        tix_result = _tix_04(c)
        watch_result = _watch_22_10(c)
        assert tix_result.severity == "flag"
        assert watch_result.severity == "pass"


# ---------------------------------------------------------------------------
# Representative guard — WATCH/TIX/EVOLVE rules must not run without their representative
# ---------------------------------------------------------------------------

class TestRepresentativeGuard:
    def test_watch_rules_not_in_result_when_no_watch_creditor(self):
        payload = _base_payload()
        result = assess_case(payload, detected_representatives=set())
        rule_ids = [r.rule_id for r in result["hard_blocks"] + result["flags"] + result["info"]]
        watch_ids = [rid for rid in rule_ids if rid.startswith("WATCH")]
        assert watch_ids == [], f"WATCH rules fired without WATCH creditor: {watch_ids}"

    def test_tix_rules_not_in_result_when_no_tix_creditor(self):
        payload = _base_payload()
        result = assess_case(payload, detected_representatives=set())
        rule_ids = [r.rule_id for r in result["hard_blocks"] + result["flags"] + result["info"]]
        tix_ids = [rid for rid in rule_ids if rid.startswith("TIX")]
        assert tix_ids == [], f"TIX rules fired without TIX creditor: {tix_ids}"

    def test_evolve_rules_not_in_result_when_no_evolve_creditor(self):
        payload = _base_payload()
        result = assess_case(payload, detected_representatives=set())
        rule_ids = [r.rule_id for r in result["hard_blocks"] + result["flags"] + result["info"]]
        evolve_ids = [rid for rid in rule_ids if rid.startswith("EVOLVE")]
        assert evolve_ids == [], f"EVOLVE rules fired without EVOLVE creditor: {evolve_ids}"

    def test_watch_rules_fire_when_watch_in_representatives(self):
        payload = _base_payload()
        result = assess_case(payload, detected_representatives={"WATCH"})
        all_ids = set(
            r.rule_id for r in result["hard_blocks"] + result["flags"] + result["info"] + result["passed"]
        )
        assert any(rid.startswith("WATCH") for rid in all_ids), "WATCH rules should run when WATCH detected"


# ---------------------------------------------------------------------------
# End-to-end: sample payload from the spec
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_sample_payload_does_not_crash(self):
        payload = {
            "applicationId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "status": "under_review",
            "phase": "assessment",
            "clientInfo": {"dateOfBirth": "1985-06-15"},
            "creditors": [
                {
                    "id": "uuid1",
                    "creditor_name": "Barclays Bank",
                    "account_reference": "123456789",
                    "balance": "5400.00",
                    "monthly_repayment": "150.00",
                    "creditor_type": "unsecured_loan",
                }
            ],
            "gold_transactions": [
                {
                    "id": "uuid2",
                    "description": "BARCLAYS LOAN REP",
                    "amount": "150.00",
                    "category": "Financial Liability",
                    "transaction_type": "money_out",
                    "signed_amount": -150.00,
                    "source_doc_type": "bank_statement",
                    "is_excluded": False,
                }
            ],
            "mortgage_details": [
                {
                    "lender_name": "Nationwide",
                    "balance": "150000.00",
                    "monthly_payment": "850.00",
                    "is_joint": False,
                }
            ],
            "financial_summary": {
                "total_income": 2500.00,
                "total_expenditure": 1800.00,
                "net_balance": 700.00,
                "income_source": "payslip",
                "documents": {},
            },
            "evidence_ledger": [
                {"category": "debt", "source": "creditor_report", "value": 6650.50, "verified": True}
            ],
            "documents": [
                {
                    "document_type": "bank_statement",
                    "file_name": "bank_statement_jan.pdf",
                    "extracted_data": {
                        "is_valid": True,
                        "account_holder": "John Doe",
                        "statement_date": date.today().isoformat(),
                        "transactions": [],
                    },
                    "is_valid": True,
                },
                {
                    "document_type": "payslip",
                    "file_name": "payslip_jan.pdf",
                    "extracted_data": {
                        "statement_date": date.today().isoformat(),
                    },
                    "is_valid": True,
                },
            ],
            "crm_data": {
                "crm_id": "CRM-98765",
                "total_unsecured_debt": 6650.50,
                "total_secured_debt": 150000.00,
            },
            "has_property": True,
            "has_vehicle": False,
            "has_mortgage": True,
            "has_job": True,
            "has_uc_journal": False,
        }

        result = assess_case(payload, detected_representatives=set())
        assert isinstance(result, dict)
        assert "hard_blocks" in result
        assert "flags" in result
        assert "overall" in result

    def test_sample_tig01_passes_on_spec_debt(self):
        """crm_data.total_unsecured_debt = 6650.50 — must pass TIG-01."""
        payload = _base_payload()
        payload["crm_data"] = {"total_unsecured_debt": 6650.50}
        result = assess_case(payload, detected_representatives=set())
        block_ids = [r.rule_id for r in result["hard_blocks"]]
        assert "TIG-01" not in block_ids

    def test_no_watch_tix_evolve_rules_fire_on_spec_payload(self):
        """Spec payload has no WATCH/TIX/EVOLVE creditors."""
        payload = _base_payload()
        result = assess_case(payload, detected_representatives=set())
        all_triggered = result["hard_blocks"] + result["flags"]
        rep_rules = [r for r in all_triggered if r.rule_id.startswith(("WATCH", "TIX", "EVOLVE"))]
        assert rep_rules == []

    def test_phantom_majority_threshold_never_appears(self):
        """majority_threshold must not appear anywhere in engine output."""
        payload = _base_payload()
        result = assess_case(payload, detected_representatives=set())
        all_results = result["hard_blocks"] + result["flags"] + result["info"] + result["passed"]
        ids = [r.rule_id for r in all_results]
        assert "majority_threshold" not in ids
        assert not any("majority_threshold" in r.message for r in all_results)


# ---------------------------------------------------------------------------
# TODO field handling — must return flag not exception
# ---------------------------------------------------------------------------

class TestTODOFieldGracefulHandling:
    def test_missing_vehicle_value_returns_flag_not_exception(self):
        payload = _base_payload()
        # vehicle_value absent from payload
        c = _parse_case(payload)
        r = _watch_22_9(c)
        assert r.severity == "flag"
        assert "TODO" in r.message

    def test_missing_children_returns_flag_not_exception(self):
        payload = _base_payload()
        c = _parse_case(payload)
        from criteria_engine import _watch_22_7
        r = _watch_22_7(c)
        assert r.severity == "flag"
        assert "TODO" in r.message

    def test_missing_antecedent_transactions_returns_flag(self):
        payload = _base_payload()
        c = _parse_case(payload)
        from criteria_engine import _watch_22_13
        r = _watch_22_13(c)
        assert r.severity == "flag"
        assert "TODO" in r.message
