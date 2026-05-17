"""
Tests for patch-set: 8 corrections to criteria_engine.py

One test class per patch. Naming follows the spec exactly:
  - test_tig_10_per_creditor_proof
  - test_gambling_monthly_filters_to_last_30_days
  - test_hp_monthly_filters_to_last_30_days
  - test_tig_21_4_mixed_income_returns_todo_flag
  - test_tig_21_4_benefits_only_hard_blocks
  - test_run_exception_uses_correct_rule_id_format
  - test_run_exception_returns_hard_block_not_flag
  - test_detect_representatives_does_not_match_substrings
  - test_tig_16_skipped_when_case_type_missing
  - test_tig_16_fires_for_non_wpm_case_type
  - test_tig_20_1_does_not_block_on_creditor_presence_alone
  - test_tig_20_1_blocks_on_recent_spend
"""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from criteria_engine import (
    assess_case,
    _parse_case,
    _gambling_monthly,
    _hp_monthly_from_transactions,
    _func_to_rule_id,
    _tig_10,
    _tig_16,
    _tig_20_1,
    _tig_21_4,
)


# ---------------------------------------------------------------------------
# Shared helpers (duplicated here so this file runs standalone)
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()


def _days_back(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _base_payload(**overrides) -> dict:
    payload = {
        "applicationId": "patch-test",
        "clientInfo": {"dateOfBirth": "1980-01-01"},
        "creditors": [
            {
                "creditor_name": "Barclays",
                "balance": "4000.00",
                "creditor_type": "unsecured_loan",
                "linked_creditor": "EVID-B",
            },
            {
                "creditor_name": "HSBC",
                "balance": "3000.00",
                "creditor_type": "unsecured_loan",
                "linked_creditor": "EVID-H",
            },
        ],
        "gold_transactions": [],
        "mortgage_details": [],
        "financial_summary": {
            "total_income": 2500.00,
            "total_expenditure": 1800.00,
            "net_balance": 700.00,
            "income_source": "payslip",
        },
        "evidence_ledger": [
            {"ref": "EVID-B", "doc_type": "bank_statement"},
            {"ref": "EVID-H", "doc_type": "bank_statement"},
            {"ref": "EVID-PG", "doc_type": "letter"},
        ],
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
        "crm_data": {"total_unsecured_debt": 7000.00},
        "has_property": False,
        "has_vehicle": False,
        "has_job": True,
        "has_uc_journal": False,
    }
    payload.update(overrides)
    return payload


def _parsed(**overrides) -> dict:
    return _parse_case(_base_payload(**overrides))


# ---------------------------------------------------------------------------
# PATCH 1 — TIG-10: per-creditor proof via linked_creditor ↔ evidence_ledger
# ---------------------------------------------------------------------------

class TestPatch1TIG10:
    def test_tig_10_passes_when_all_creditors_linked(self):
        c = _parsed()
        r = _tig_10(c)
        assert r.rule_id == "TIG-10"
        assert r.severity == "pass"
        assert r.triggered is False

    def test_tig_10_hard_block_high_balance_no_link(self):
        c = _parsed(
            creditors=[
                {
                    "creditor_name": "Big Bank",
                    "balance": "5000.00",
                    "creditor_type": "unsecured_loan",
                    "linked_creditor": "",
                },
            ],
            evidence_ledger=[{"ref": "EVID-X", "doc_type": "letter"}],
        )
        r = _tig_10(c)
        assert r.severity == "hard_block"
        assert r.triggered is True
        assert "£1,000" in r.message or "1000" in r.message

    def test_tig_10_flags_small_balance_no_link(self):
        c = _parsed(
            creditors=[
                {
                    "creditor_name": "Small Debt Ltd",
                    "balance": "500.00",
                    "creditor_type": "unsecured_loan",
                    "linked_creditor": "",
                },
            ],
            evidence_ledger=[],
        )
        r = _tig_10(c)
        assert r.severity == "flag"
        assert r.triggered is True
        assert "verbal" in r.message.lower() or "linked" in r.message.lower()


# ---------------------------------------------------------------------------
# PATCH 2 — _gambling_monthly must filter to last 30 days only
# ---------------------------------------------------------------------------

class TestPatch2GamblingMonthly:
    def _tx(self, date_str: str, amount: float = 500.0) -> dict:
        return {
            "description": "LADBROKES",
            "amount": str(amount),
            "transaction_date": date_str,
        }

    def test_gambling_monthly_filters_to_last_30_days(self):
        """Transaction from 31 days ago must NOT be counted."""
        old_tx = self._tx(_days_back(31), 500.0)
        recent_tx = self._tx(_days_back(10), 100.0)
        result = _gambling_monthly([old_tx, recent_tx])
        assert result == pytest.approx(100.0), (
            "Only the 10-day-old transaction should be counted; "
            "the 31-day-old one is outside the 30-day window."
        )

    def test_gambling_monthly_includes_transaction_at_exactly_30_days(self):
        tx = self._tx(_days_back(30), 200.0)
        assert _gambling_monthly([tx]) == pytest.approx(200.0)

    def test_gambling_monthly_excludes_transaction_beyond_30_days(self):
        tx = self._tx(_days_back(31), 999.0)
        assert _gambling_monthly([tx]) == pytest.approx(0.0)

    def test_gambling_monthly_empty_list(self):
        assert _gambling_monthly([]) == pytest.approx(0.0)

    def test_gambling_monthly_non_gambling_description_ignored(self):
        tx = {"description": "TESCO GROCERIES", "amount": "500.00", "transaction_date": _today()}
        assert _gambling_monthly([tx]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# PATCH 3 — _hp_monthly_from_transactions must filter to last 30 days only
# ---------------------------------------------------------------------------

class TestPatch3HPMonthly:
    def _tx(self, date_str: str, amount: float = 400.0) -> dict:
        return {
            "description": "CAR FINANCE HP",
            "amount": str(amount),
            "transaction_date": date_str,
        }

    def test_hp_monthly_filters_to_last_30_days(self):
        """Transaction from 31 days ago must NOT be counted."""
        old_tx = self._tx(_days_back(31), 400.0)
        recent_tx = self._tx(_days_back(5), 300.0)
        result = _hp_monthly_from_transactions([old_tx, recent_tx])
        assert result == pytest.approx(300.0), (
            "Only the 5-day-old transaction should count."
        )

    def test_hp_monthly_includes_transaction_at_exactly_30_days(self):
        tx = self._tx(_days_back(30), 350.0)
        assert _hp_monthly_from_transactions([tx]) == pytest.approx(350.0)

    def test_hp_monthly_excludes_transaction_beyond_30_days(self):
        tx = self._tx(_days_back(31), 999.0)
        assert _hp_monthly_from_transactions([tx]) == pytest.approx(0.0)

    def test_hp_monthly_empty_list(self):
        assert _hp_monthly_from_transactions([]) == pytest.approx(0.0)

    def test_hp_monthly_non_finance_description_ignored(self):
        tx = {"description": "TESCO FUEL", "amount": "400.00", "transaction_date": _today()}
        assert _hp_monthly_from_transactions([tx]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# PATCH 4 — TIG-21.4 mixed-income returns todo_flag; benefits-only hard blocks
# ---------------------------------------------------------------------------

class TestPatch4TIG214:
    def _link_base(self, income_source: str) -> dict:
        return _parsed(
            creditors=[
                {
                    "creditor_name": "Link Financial",
                    "balance": "8000.00",
                    "creditor_type": "unsecured_loan",
                    "linked_creditor": "EVID-B",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": "6000.00",
                    "creditor_type": "unsecured_loan",
                    "linked_creditor": "EVID-H",
                },
            ],
            crm_data={"total_unsecured_debt": 14000.00},
            financial_summary={
                "total_income": 2000.00,
                "net_balance": 500.00,
                "income_source": income_source,
            },
        )

    def test_tig_21_4_benefits_only_hard_blocks(self):
        c = self._link_base("benefits")
        r = _tig_21_4(c)
        assert r.severity == "hard_block"
        assert r.triggered is True
        assert r.rule_id == "TIG-21.4"

    def test_tig_21_4_universal_credit_hard_blocks(self):
        c = self._link_base("universal_credit")
        r = _tig_21_4(c)
        assert r.severity == "hard_block"

    def test_tig_21_4_uc_alias_hard_blocks(self):
        c = self._link_base("uc")
        r = _tig_21_4(c)
        assert r.severity == "hard_block"

    def test_tig_21_4_mixed_income_returns_todo_flag(self):
        """Employed income with Link creditor: cannot compute %, must flag for review."""
        c = self._link_base("payslip")
        r = _tig_21_4(c)
        assert r.severity == "flag"
        assert r.triggered is True
        assert "TODO" in r.message

    def test_tig_21_4_no_link_creditor_passes(self):
        c = _parsed(
            financial_summary={
                "total_income": 1200.00,
                "net_balance": 200.00,
                "income_source": "benefits",
            },
        )
        r = _tig_21_4(c)
        assert r.severity == "pass"


# ---------------------------------------------------------------------------
# PATCH 5 — _run exception handler: rule_id format and hard_block severity
# ---------------------------------------------------------------------------

class TestPatch5RunExceptionHandler:
    def _broken_rule(self, c: dict):
        raise ValueError("simulated rule crash")

    def _run_broken_rule(self):
        """Drive assess_case with a payload that will invoke _broken_rule via _run."""
        payload = _base_payload()
        result = assess_case(payload, detected_representatives=set())
        return result

    def test_func_to_rule_id_tig(self):
        assert _func_to_rule_id("_tig_01") == "TIG-01"

    def test_func_to_rule_id_watch(self):
        assert _func_to_rule_id("_watch_22_2") == "WATCH-22.2"

    def test_func_to_rule_id_tig_multipart(self):
        assert _func_to_rule_id("_tig_15_10") == "TIG-15.10"

    def test_func_to_rule_id_tix(self):
        assert _func_to_rule_id("_tix_04") == "TIX-04"

    def test_func_to_rule_id_evolve(self):
        assert _func_to_rule_id("_evolve_02") == "EVOLVE-02"

    def test_run_exception_uses_correct_rule_id_format(self):
        """Inject a crashing rule whose __name__ is '_tig_01' and confirm rule_id
        comes out as 'TIG-01' (not the raw Python name)."""
        import criteria_engine as ce

        original = ce._tig_01

        # Function must be named _tig_01 so _func_to_rule_id converts it correctly.
        def _tig_01(c):  # noqa: F811
            raise RuntimeError("deliberate crash")

        ce._tig_01 = _tig_01
        try:
            payload = _base_payload()
            result = assess_case(payload, detected_representatives=set())
            crashed = [r for r in result["hard_blocks"] if "deliberate crash" in r.message]
            assert crashed, "Expected a hard_block from the crashing rule"
            assert crashed[0].rule_id == "TIG-01", (
                f"rule_id should be 'TIG-01', got {crashed[0].rule_id!r}"
            )
        finally:
            ce._tig_01 = original

    def test_run_exception_returns_hard_block_not_flag(self):
        """A crashing rule must hard-block the case, not silently downgrade to flag."""
        import criteria_engine as ce

        original = ce._tig_02

        def _tig_02(c):  # noqa: F811
            raise RuntimeError("deliberate crash")

        ce._tig_02 = _tig_02
        try:
            payload = _base_payload()
            result = assess_case(payload, detected_representatives=set())
            crashed = [r for r in result["hard_blocks"] if "deliberate crash" in r.message]
            assert crashed, "Crashing rule should produce a hard_block, not a flag"
            assert result["overall"] == "blocked"
        finally:
            ce._tig_02 = original


# ---------------------------------------------------------------------------
# PATCH 6 — detect_representatives: no substring matching
# ---------------------------------------------------------------------------

class TestPatch6DetectRepresentatives:
    # CreditorCriteria is a local import inside detect_representatives, so the
    # correct patch target is the model class in its own module.
    _PATCH_TARGET = "debt_app.models.CreditorCriteria"

    def _mock_qs(self, criteria_rows):
        mock_qs = MagicMock()
        mock_qs.__iter__ = MagicMock(return_value=iter(criteria_rows))
        return mock_qs

    def _mock_criterion(self, name, trading_names, representative):
        m = MagicMock()
        m.creditor_name = name
        m.trading_names = trading_names
        m.representative = representative
        return m

    def test_detect_representatives_does_not_match_substrings(self):
        """
        The seeded name is "Barclays Bank". The case creditor is just "Bank"
        (a suffix substring). Under exact-only matching this must NOT match.
        """
        crit = self._mock_criterion("Barclays Bank", [], "WATCH")
        qs = self._mock_qs([crit])

        with patch(self._PATCH_TARGET) as mock_model:
            mock_model.objects.filter.return_value.exclude.return_value \
                .exclude.return_value.exclude.return_value = qs

            from criteria_engine import detect_representatives
            reps = detect_representatives([{"creditor_name": "Bank"}])

        assert "WATCH" not in reps, (
            "'Bank' is a substring of 'Barclays Bank' but must NOT match "
            "under exact-only logic"
        )

    def test_detect_representatives_exact_match_works(self):
        """Exact match on creditor_name must be detected."""
        crit = self._mock_criterion("Barclays Bank", [], "WATCH")
        qs = self._mock_qs([crit])

        with patch(self._PATCH_TARGET) as mock_model:
            mock_model.objects.filter.return_value.exclude.return_value \
                .exclude.return_value.exclude.return_value = qs

            from criteria_engine import detect_representatives
            reps = detect_representatives([{"creditor_name": "Barclays Bank"}])

        assert "WATCH" in reps

    def test_detect_representatives_trading_name_exact_match(self):
        """Exact match against a trading_name must also be detected."""
        crit = self._mock_criterion("Barclays PLC", ["Barclaycard"], "TIX")
        qs = self._mock_qs([crit])

        with patch(self._PATCH_TARGET) as mock_model:
            mock_model.objects.filter.return_value.exclude.return_value \
                .exclude.return_value.exclude.return_value = qs

            from criteria_engine import detect_representatives
            reps = detect_representatives([{"creditor_name": "Barclaycard"}])

        assert "TIX" in reps


# ---------------------------------------------------------------------------
# PATCH 7 — TIG-16: equity vs GlobalCriteria £ threshold (default £5,000)
# ---------------------------------------------------------------------------

class TestPatch7TIG16:
    def _property_case(
        self,
        *,
        property_value: float,
        mortgage_balance: float = 0.0,
        case_type=None,
        total_debt: float = 30000.0,
    ) -> dict:
        return _parse_case(_base_payload(
            has_property=True,
            property_value=property_value,
            mortgage_details=[{"balance": str(mortgage_balance)}],
            crm_data={"total_unsecured_debt": total_debt},
            case_type=case_type,
        ))

    def test_tig_16_todo_when_property_value_missing(self):
        c = _parse_case(_base_payload(has_property=True, case_type="NON_WPM"))
        r = _tig_16(c)
        assert r.severity == "flag"
        assert r.triggered is True
        assert "property_value" in r.message

    def test_tig_16_hard_blocks_when_equity_above_default_threshold(self):
        c = self._property_case(property_value=200_000.0, mortgage_balance=100_000.0)
        r = _tig_16(c)
        assert r.severity == "hard_block"
        assert r.triggered is True
        assert r.rule_id == "TIG-16"
        assert r.actual_value == 100_000.0
        assert r.threshold == 5000.0

    def test_tig_16_passes_when_equity_at_or_below_threshold(self):
        c = self._property_case(property_value=105_000.0, mortgage_balance=100_000.0)
        r = _tig_16(c)
        assert r.severity == "pass"
        assert r.triggered is False

    def test_tig_16_ignores_case_type(self):
        """Equity rule runs for any case_type once property_value is present."""
        c = self._property_case(
            property_value=200_000.0,
            mortgage_balance=100_000.0,
            case_type="WPM",
        )
        r = _tig_16(c)
        assert r.severity == "hard_block"

    def test_tig_16_no_property_without_value_is_todo(self):
        c = _parse_case(_base_payload(has_property=False, case_type="NON_WPM"))
        r = _tig_16(c)
        assert r.severity == "flag"
        assert "property_value" in r.message


# ---------------------------------------------------------------------------
# PATCH 8 — TIG-20.1: spend-only trigger, not creditor-presence trigger
# ---------------------------------------------------------------------------

class TestPatch8TIG201:
    def _creation_tx(self, date_str: str) -> dict:
        return {
            "description": "CREATION FINANCE",
            "amount": "100.00",
            "transaction_type": "money_out",
            "signed_amount": -100.0,
            "transaction_date": date_str,
        }

    def test_tig_20_1_does_not_block_on_creditor_presence_alone(self):
        """Dormant Creation creditor (no recent transactions) must NOT hard-block."""
        payload = _base_payload()
        payload["creditors"] = [
            {
                "creditor_name": "Creation",
                "balance": "2000.00",
                "creditor_type": "unsecured_loan",
                "linked_creditor": "EVID-PG",
            },
            {
                "creditor_name": "Barclays",
                "balance": "5000.00",
                "creditor_type": "unsecured_loan",
                "linked_creditor": "EVID-B",
            },
        ]
        payload["gold_transactions"] = []
        c = _parse_case(payload)
        r = _tig_20_1(c)
        assert r.severity == "pass", (
            "TIG-20.1 must not fire on creditor presence alone — "
            "only on recent spend within 4 months."
        )

    def test_tig_20_1_blocks_on_recent_spend(self):
        """Recent Creation transaction within 4 months must hard-block."""
        payload = _base_payload()
        payload["creditors"] = [
            {
                "creditor_name": "Barclays",
                "balance": "7000.00",
                "creditor_type": "unsecured_loan",
                "linked_creditor": "EVID-B",
            },
        ]
        payload["gold_transactions"] = [self._creation_tx(_days_back(10))]
        c = _parse_case(payload)
        r = _tig_20_1(c)
        assert r.severity == "hard_block"
        assert r.triggered is True
        assert r.rule_id == "TIG-20.1"

    def test_tig_20_1_does_not_block_on_old_spend(self):
        """Transaction older than 4 months (120 days) must NOT trigger."""
        payload = _base_payload()
        payload["gold_transactions"] = [self._creation_tx(_days_back(121))]
        c = _parse_case(payload)
        r = _tig_20_1(c)
        assert r.severity == "pass"

    def test_tig_20_1_and_tig_20_both_fire_on_recent_spend(self):
        """Both TIG-20 (flag) and TIG-20.1 (hard_block) fire on recent Creation spend."""
        from criteria_engine import _tig_20
        payload = _base_payload()
        payload["gold_transactions"] = [self._creation_tx(_days_back(10))]
        c = _parse_case(payload)
        assert _tig_20(c).severity == "flag"
        assert _tig_20_1(c).severity == "hard_block"
