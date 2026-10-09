"""
Aryza income extraction (AryzaClient._fetch_income_data) running its real SQL
against minimal client_sfs / client_income / client_expenses tables in the test
database.

Row selection: the client_income row linked to the newest active SFS
(client_income.statement_id = client_sfs.id); if there is none, the client's
newest income row. Previously an unordered "WHERE clientid LIMIT 1" returned the
oldest (usually blank) row.
"""

from django.db import connection
from django.test import TestCase

from debt_app.aryza_client import _INCOME_COLUMNS as _READ_COLUMNS, AryzaClient, CaseData

CLIENT = 601

# Columns the extraction reads: every amount with its "<column>_frequency",
# as in the real Aryza client_income table.
_INCOME_COLUMNS = [name for col, _, _ in _READ_COLUMNS for name in (col, f"{col}_frequency")]


class _IncomeTablesTestCase(TestCase):
    """Minimal Aryza tables in the test DB, and helpers (no tests of its own)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cols = ", ".join(f"{c} TEXT" if c.endswith("_frequency") else f"{c} DECIMAL(11,2)" for c in _INCOME_COLUMNS)
        with connection.cursor() as c:
            c.execute("CREATE TABLE client_sfs (id INTEGER PRIMARY KEY, clientid INTEGER, active INTEGER)")
            c.execute(f"CREATE TABLE client_income (id INTEGER PRIMARY KEY, clientid INTEGER, statement_id INTEGER, "
                      f"statement_type TEXT, {cols})")
            c.execute("CREATE TABLE client_expenses (id INTEGER PRIMARY KEY, clientid INTEGER, type TEXT, "
                      "field TEXT, value DECIMAL(11,2), statement_id INTEGER, frequency TEXT)")

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as c:
            for t in ("client_sfs", "client_income", "client_expenses"):
                c.execute(f"DROP TABLE {t}")
        super().tearDownClass()

    # ---- helpers -----------------------------------------------------------

    def _sfs(self, sfs_id, active=1, clientid=CLIENT):
        with connection.cursor() as c:
            c.execute("INSERT INTO client_sfs VALUES (%s, %s, %s)", [sfs_id, clientid, active])

    def _income(self, row_id, statement_id=None, statement_type=None, clientid=CLIENT, **values):
        cols = ["id", "clientid", "statement_id", "statement_type", *values]
        with connection.cursor() as c:
            c.execute(f"INSERT INTO client_income ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                      [row_id, clientid, statement_id, statement_type, *values.values()])

    def _extract(self, conn=connection):
        case = CaseData()
        case.clientid = CLIENT
        client = AryzaClient()
        client._fetch_income_data(conn, case, CLIENT)
        client._calculate_totals(case)
        return case

    def _total(self):
        return self._extract().income["total"]

    def _audit(self, case):
        return next(a for a in case.audit_log if a["table"] == "client_income")


class AryzaIncomeExtractionTests(_IncomeTablesTestCase):

    # ---- row selection -------------------------------------------------------

    def test_current_sfs_income_wins_over_old_blank_row(self):
        self._sfs(10, active=0)
        self._income(1, statement_id=10, earnings_net=0)
        self._sfs(20)
        self._income(2, statement_id=20, earnings_net="2500.00")
        case = self._extract()
        self.assertEqual(case.income["total"], 250_000)
        self.assertEqual(self._audit(case)["details"], "Income row from current SFS")

    def test_current_sfs_row_wins_even_when_not_the_newest_row(self):
        """Guards against a plain ORDER BY id DESC: the newest row belongs to an inactive SFS."""
        self._sfs(20)
        self._income(2, statement_id=20, earnings_net="3000.00")
        self._sfs(30, active=0)
        self._income(3, statement_id=30, earnings_net="1800.00")
        self.assertEqual(self._total(), 300_000)

    def test_only_the_current_sfs_row_is_used_among_many(self):
        for i, amount in enumerate(("0", "1200.00", "1500.00", "0"), start=1):
            self._sfs(i * 10, active=0)
            self._income(i, statement_id=i * 10, earnings_net=amount)
        self._income(5, statement_id=None, earnings_net="999.00")
        self._sfs(50)
        self._income(6, statement_id=50, earnings_net="2100.00")
        self._income(7, statement_id=None, earnings_net="4444.00")  # newer, but not linked
        self.assertEqual(self._total(), 210_000)

    def test_newest_active_sfs_is_used_when_several_are_active(self):
        self._sfs(10)
        self._income(1, statement_id=10, earnings_net="900.00")
        self._sfs(20)
        self._income(2, statement_id=20, earnings_net="2000.00")
        self.assertEqual(self._total(), 200_000)

    def test_inactive_sfs_income_not_used_when_active_sfs_has_a_row(self):
        self._sfs(10)
        self._income(1, statement_id=10, earnings_net="1000.00")
        self._sfs(20, active=0)  # newer but inactive
        self._income(2, statement_id=20, earnings_net="5000.00")
        self.assertEqual(self._total(), 100_000)

    def test_cfs_row_with_same_statement_id_is_not_the_sfs_row(self):
        self._sfs(10)
        self._income(1, statement_id=10, earnings_net="1700.00")
        self._income(2, statement_id=10, statement_type="cfs", earnings_net="50.00")
        self._income(3, statement_id=10, statement_type="sfs", earnings_net="1750.00")
        self.assertEqual(self._total(), 175_000)

    def test_genuine_zero_on_current_row_is_not_replaced_by_older_income(self):
        self._sfs(10, active=0)
        self._income(1, statement_id=10, earnings_net="2200.00")
        self._sfs(20)
        self._income(2, statement_id=20, earnings_net=0, benefit_universal_credit=0)
        case = self._extract()
        self.assertEqual(case.income["total"], 0)
        self.assertEqual(self._audit(case)["status"], "FOUND")

    # ---- fallback -------------------------------------------------------------

    def test_no_row_linked_to_current_sfs_falls_back_to_newest_row(self):
        self._sfs(20)
        self._income(1, statement_id=None, earnings_net="800.00")
        self._income(2, statement_id=None, earnings_net="1600.00")
        case = self._extract()
        self.assertEqual(case.income["total"], 160_000)
        self.assertEqual(self._audit(case)["details"], "Income row from newest row (no current SFS income row)")

    def test_no_active_sfs_falls_back_to_newest_row(self):
        self._sfs(10, active=0)
        self._income(1, statement_id=10, earnings_net="700.00")
        self._income(2, statement_id=None, earnings_net="1400.00")
        self.assertEqual(self._total(), 140_000)

    def test_no_income_rows_is_recorded_as_empty(self):
        self._sfs(10)
        self._income(1, clientid=999, statement_id=10, earnings_net="3000.00")  # another client's row
        case = self._extract()
        self.assertEqual(case.income["total"], 0)
        self.assertEqual(self._audit(case)["status"], "EMPTY")

    def test_query_failure_is_recorded_as_error_not_found(self):
        """Existing contract: the failure is logged and audited; income stays at its default."""
        case = self._extract(conn=_FailingIncomeConnection())
        self.assertEqual(case.income["total"], 0)
        self.assertEqual(self._audit(case)["status"], "ERROR")

    # ---- existing calculation on the selected row -----------------------------

    def test_existing_income_calculation_is_unchanged(self):
        self._sfs(20)
        self._income(
            1, statement_id=20,
            earnings_net="300.00", earnings_net_frequency="weekly",   # 300 x 52 / 12 = 1,300
            earnings_partner_net="1000.00", earnings_partner_net_frequency="monthly",
            benefit_universal_credit="200.00", benefit_universal_credit_frequency="fortnightly",  # 433.33
            benefit_pip="400.00", benefit_pip_frequency="4_weekly",   # 433.33
            benefit_child="100.00", pension_state="50.00", student_loan="25.00",
            non_dependant_contributions="60.00", lodger_income="40.00",
        )
        case = self._extract()
        self.assertEqual(case.income["employment"], 130_000 + 100_000)
        self.assertEqual(case.income["universal_credit"], 43_333)
        self.assertEqual(case.income["pip"], 43_333)
        self.assertEqual(case.income["other_benefits"], 10_000 + 5_000 + 2_500)
        self.assertEqual(case.income["third_party_contribution"], 10_000)
        self.assertEqual(case.income["total"], 230_000 + 43_333 + 43_333 + 17_500 + 10_000)
        self.assertEqual(case.employment_status, "employed")


class AryzaIncomeFrequencyTests(_IncomeTablesTestCase):
    """Every income amount is converted to monthly with its own Aryza frequency."""

    def _row(self, **values):
        self._sfs(10)
        self._income(1, statement_id=10, **values)
        return self._extract()

    def test_each_frequency_for_child_benefit(self):
        for freq, expected in (("weekly", 11_700), ("fortnightly", 5_850), ("4_weekly", 2_925),
                               ("monthly", 2_700), (None, 2_700)):
            with self.subTest(freq=freq):
                with connection.cursor() as c:
                    c.execute("DELETE FROM client_sfs"); c.execute("DELETE FROM client_income")
                case = self._row(benefit_child="27.00", benefit_child_frequency=freq)
                self.assertEqual(case.income["other_benefits"], expected)

    def test_representative_benefits_pensions_student_and_lodger(self):
        case = self._row(
            benefit_esa="300.00", benefit_esa_frequency="fortnightly",               # 650.00
            benefit_carers_allowance="86.00", benefit_carers_allowance_frequency="weekly",  # 372.66
            benefit_housing="775.00", benefit_housing_frequency="4_weekly",           # 839.58
            pension_state="241.25", pension_state_frequency="weekly",                 # 1,045.41
            pension_private="400.00", pension_private_frequency="monthly",            # 400.00
            student_loan="317.00", student_loan_frequency="fortnightly",              # 686.83
            lodger_income="100.00", lodger_income_frequency="weekly",                 # 433.33 (third party)
        )
        self.assertEqual(case.income["other_benefits"], 65_000 + 37_266 + 83_958 + 104_541 + 40_000 + 68_683)
        self.assertEqual(case.income["third_party_contribution"], 43_333)

    def test_partial_pennies_truncate_like_the_existing_helper(self):
        # 26.25 x 52 / 12 = 113.75 exactly; 86.00 x 52 / 12 = 372.666... -> 372.66
        case = self._row(benefit_child="26.25", benefit_child_frequency="weekly",
                         benefit_aa="86.00", benefit_aa_frequency="weekly")
        self.assertEqual(case.income["other_benefits"], 11_375 + 37_266)

    def test_missing_and_zero_amounts_add_nothing_whatever_the_frequency(self):
        case = self._row(earnings_net="1000.00", benefit_child=None, benefit_child_frequency="weekly",
                         benefit_esa=0, benefit_esa_frequency="fortnightly")
        self.assertEqual(case.income["other_benefits"], 0)
        self.assertEqual(case.income["total"], 100_000)
        self.assertEqual(case.non_monthly_income, [])

    def test_already_converted_types_are_unchanged(self):
        case = self._row(
            earnings_net="463.00", earnings_net_frequency="weekly",                   # 2,006.33
            earnings_partner_net="1100.00", earnings_partner_net_frequency="fortnightly",  # 2,383.33
            benefit_universal_credit="416.00", benefit_universal_credit_frequency="fortnightly",  # 901.33
            benefit_dla="494.00", benefit_dla_frequency="4_weekly",                   # 535.16
            benefit_pip="400.00", benefit_pip_frequency="monthly",
        )
        self.assertEqual(case.income["employment"], 200_633 + 238_333)
        self.assertEqual(case.income["universal_credit"], 90_133)
        self.assertEqual(case.income["dla"], 53_516)
        self.assertEqual(case.income["pip"], 40_000)

    def test_non_monthly_items_are_listed_for_display(self):
        case = self._row(benefit_child="27.00", benefit_child_frequency="weekly",
                         benefit_pip="400.00", benefit_pip_frequency="monthly")
        self.assertEqual(case.non_monthly_income, [
            {"source": "Child Benefit", "amount": 27.0, "frequency": "weekly", "monthly": 117.0},
        ])

    # ---- income_recorded ----------------------------------------------------

    def test_entered_amounts_mean_income_is_recorded_even_when_zero(self):
        self.assertTrue(self._row(earnings_net=0).income_recorded)

    def test_blank_row_means_income_not_recorded(self):
        case = self._row()
        self.assertIs(case.income_recorded, False)
        self.assertEqual(case.income["total"], 0)

    def test_no_income_row_means_income_not_recorded(self):
        self._sfs(10)
        self.assertIs(self._extract().income_recorded, False)

    def test_query_failure_leaves_income_recorded_undetermined(self):
        self.assertIsNone(self._extract(conn=_FailingIncomeConnection()).income_recorded)


class _FailingIncomeConnection:
    """Cursor whose client_income queries fail; everything else is a no-op."""

    def cursor(self):
        return _FailingCursor()


class _FailingCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if "client_income" in sql or "client_sfs" in sql:
            raise RuntimeError("Lost connection to MySQL server")

    def fetchone(self):
        return (None,)

    def fetchall(self):
        return []
