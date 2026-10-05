"""
TIG-19 / TIX-01: a payment to an account the client already holds is a
likely repayment, not new spend.

Case 411322 (Lucy Carr): "VERY BOOTLE £50.00" (27 Aug) and "FASHION WORLD
MANCHESTER £6.72" (28 Aug) -- payments to Shop Direct (opened 20/11/2023,
£864 owing) and Fashion World (opened 27/09/2023, £165 owing) -- were two hard
blocks reading "recent spend". They are now a flag asking the caseworker to
confirm. A payment that no existing account explains still hard-blocks.
"""
from django.test import TestCase

from debt_app.engine.criteria import (
    _parse_case,
    _recent_transactions_matching,
    _tig_19,
    _tig_19_review,
    _tix_01,
    assess_case,
)

ASSESSMENT_DATE = "2026-10-05"

VERY_PAYMENT = {
    "transaction_date": "2026-08-27", "description": "VERY BOOTLE",
    "amount": 50.0, "transaction_type": "money_out",
}
FASHION_WORLD_PAYMENT = {
    "transaction_date": "2026-08-28", "description": "FASHION WORLD MANCHESTER",
    "amount": 6.72, "transaction_type": "money_out",
}
SHOP_DIRECT_2023 = {"creditor_name": "Shop Direct Finance Company LTD", "balance": 864, "cr_start_date": "2023-11-20"}
FASHION_WORLD_2023 = {"creditor_name": "Fashion World", "balance": 165, "cr_start_date": "2023-09-27"}


def _case(creditors, transactions):
    return _parse_case({
        "assessment_date": ASSESSMENT_DATE,
        "creditors": creditors,
        "gold_transactions": transactions,
    })


class ShopDirectRepaymentTests(TestCase):

    def test_case_411322_repayments_are_a_flag_not_a_block(self):
        c = _case([SHOP_DIRECT_2023, FASHION_WORLD_2023], [VERY_PAYMENT, FASHION_WORLD_PAYMENT])
        for rule in (_tig_19, _tix_01):
            r = rule(c)
            self.assertTrue(r.triggered, r.rule_id)
            self.assertEqual("flag", r.severity, r.rule_id)
            self.assertIn("2 payment(s)", r.message)

    def test_payment_with_no_account_on_the_case_still_blocks(self):
        # TIG-19 has no "is a creditor" gate: a Very payment with no Very
        # account is the spend the rule exists to catch.
        c = _case([{"creditor_name": "Lendable", "balance": 900, "cr_start_date": "2022-01-01"}], [VERY_PAYMENT])
        r = _tig_19(c)
        self.assertEqual("hard_block", r.severity)

    def test_account_in_the_other_group_does_not_explain_the_payment(self):
        # An old Fashion World (N Brown) account does not explain a Very payment.
        c = _case([FASHION_WORLD_2023], [VERY_PAYMENT, FASHION_WORLD_PAYMENT])
        for rule in (_tig_19, _tix_01):
            r = rule(c)
            self.assertEqual("hard_block", r.severity, r.rule_id)
            self.assertIn(" 1 transaction(s)", r.message, r.rule_id)

    def test_new_account_still_blocks(self):
        # Opened 2 months before the assessment: the payment may be new spend.
        c = _case([{**SHOP_DIRECT_2023, "cr_start_date": "2026-08-01"}], [VERY_PAYMENT])
        self.assertEqual("hard_block", _tig_19(c).severity)
        self.assertEqual("hard_block", _tix_01(c).severity)

    def test_unknown_account_age_still_blocks(self):
        c = _case([{"creditor_name": "Shop Direct Finance Company LTD", "balance": 864}], [VERY_PAYMENT])
        self.assertEqual("hard_block", _tig_19(c).severity)
        self.assertEqual("hard_block", _tix_01(c).severity)

    def test_age_from_account_age_months_when_no_start_date(self):
        c = _case([{"creditor_name": "Shop Direct", "balance": 864, "account_age_months": 34}], [VERY_PAYMENT])
        self.assertEqual("flag", _tig_19(c).severity)
        c = _case([{"creditor_name": "Shop Direct", "balance": 864, "cr_account_age_months": 34}], [VERY_PAYMENT])
        self.assertEqual("flag", _tig_19(c).severity)

    def test_n_brown_original_name_identifies_the_group(self):
        cr = {"creditor_name": "Shop Direct", "original_name": "JD Williams (N Brown Group Plc)",
              "balance": 300, "cr_start_date": "2021-01-01"}
        c = _case([cr], [FASHION_WORLD_PAYMENT])
        self.assertEqual("flag", _tig_19(c).severity)

    def test_money_in_is_not_spend(self):
        refund = {**VERY_PAYMENT, "transaction_type": "money_in"}
        c = _case([], [refund])
        self.assertEqual("flag", _tig_19(c).severity)

    def test_one_unexplained_payment_keeps_the_block(self):
        c = _case([SHOP_DIRECT_2023], [VERY_PAYMENT, FASHION_WORLD_PAYMENT])
        r = _tix_01(c)
        self.assertEqual("hard_block", r.severity)
        self.assertIn(" 1 transaction(s)", r.message)

    def test_no_matches_passes(self):
        c = _case([SHOP_DIRECT_2023], [{**VERY_PAYMENT, "description": "TESCO STORES"}])
        self.assertFalse(_tig_19(c).triggered)
        self.assertFalse(_tix_01(c).triggered)

    def test_4_month_review_unchanged(self):
        older = {**VERY_PAYMENT, "transaction_date": "2026-06-20"}  # 107 days before
        c = _case([SHOP_DIRECT_2023], [older])
        self.assertFalse(_tig_19(c).triggered)
        self.assertTrue(_tig_19_review(c).triggered)

    def test_very_is_matched_as_a_whole_word(self):
        tx = [
            {"transaction_date": "2026-09-01", "description": d, "amount": 5.0, "transaction_type": "money_out"}
            for d in ("DPD DELIVERY", "EVERYDAY LOANS", "LOWELL RECOVERY", "DISCOVERY PLUS",
                      "VERY BOOTLE", "WWW.VERY.CO.UK", "THE VERY GROUP")
        ]
        matched = _recent_transactions_matching(tx, ["very"], 90, reference=_case([], [])["assessment_date"])
        self.assertEqual(
            ["VERY BOOTLE", "WWW.VERY.CO.UK", "THE VERY GROUP"],
            [t["description"] for t in matched],
        )

    def test_assess_case_411322_has_no_shop_direct_hard_block(self):
        result = assess_case({
            "assessment_date": ASSESSMENT_DATE,
            "creditors": [SHOP_DIRECT_2023, FASHION_WORLD_2023],
            "gold_transactions": [VERY_PAYMENT, FASHION_WORLD_PAYMENT],
        }, detected_representatives={"TIX"})
        block_ids = {r.rule_id for r in result["hard_blocks"]}
        flag_ids = {r.rule_id for r in result["flags"]}
        self.assertNotIn("TIG-19", block_ids)
        self.assertNotIn("TIX-01", block_ids)
        self.assertIn("TIG-19", flag_ids)
        self.assertIn("TIX-01", flag_ids)
