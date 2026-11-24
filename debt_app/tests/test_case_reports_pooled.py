"""
Every report CAT shows is read, not the newest alone (2026-11-24, CAT: "both
of the creditor reports are main reports").

A case can hold two reports for one client -- an Experian report and an Aryza
credit search. The engine read CCJs, AoE, IVA / bankruptcy and DMP signals off
the newest report only, so a judgment printed only on the other never reached
a rule. CAT now names its reports (`credit_report_ids`); exactly those, and
only that reference's, are pooled. One report or none named: as before.
"""
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from debt_app.engine.criteria import _enrich_from_credit_report, _report_ids
from debt_app.integrations.credit_report import merge_public_signals
from debt_app.models import CreditReport

REF = "POOL-1"
CCJ_283 = {"case_number": "N9KF602H", "amount_pence": 28300, "date": "2026-03-10",
           "court_name": "Civil National Business Centre"}
CCJ_500 = {"case_number": "K1AB", "amount_pence": 50000, "date": "2025-01-02"}


def _data(ccjs=(), *, has_ccj=None, aoe=False, **public):
    return {"accounts": [{"raw_name": "ZOPA", "matched_creditor": "Zopa", "type_code": "HP",
                          "current_balance": 741000}],
            "mortgage_accounts": [], "other_accounts": [],
            "has_ccj": bool(ccjs) if has_ccj is None else has_ccj, "aoe_in_place": aoe,
            "public_information": {"has_ccj": bool(ccjs), "ccjs": list(ccjs), "ccj_count": len(ccjs),
                                   **public}}


class MergePublicSignalsTests(SimpleTestCase):

    def test_a_judgment_on_both_reports_is_one(self):
        merged = merge_public_signals([_data([CCJ_283]), _data([dict(CCJ_283)])])
        info = merged["public_information"]
        self.assertEqual((True, 1, 28300), (merged["has_ccj"], info["ccj_count"], info["ccj_total_pence"]))

    def test_a_judgment_only_on_one_report_counts(self):
        merged = merge_public_signals([_data([]), _data([CCJ_283, CCJ_500], aoe=True)])
        info = merged["public_information"]
        self.assertEqual((True, True, 2, 78300),
                         (merged["has_ccj"], merged["aoe_in_place"], info["ccj_count"], info["ccj_total_pence"]))

    def test_a_flag_set_on_any_report_is_set(self):
        merged = merge_public_signals([_data([], iva_or_bankruptcy=False, debt_management=True),
                                       _data([], iva_or_bankruptcy=True, debt_management=False)])
        info = merged["public_information"]
        self.assertEqual((True, True, False), (info["iva_or_bankruptcy"], info["debt_management"],
                                               merged["has_ccj"]))

    def test_report_ids_are_read_as_ints_once(self):
        self.assertEqual([4, 7], _report_ids(["4", 7, "x", None, 4]))
        self.assertEqual([], _report_ids(None))


class EnrichPoolsTheShownReportsTests(TestCase):

    def _report(self, data, minutes_ago):
        report = CreditReport.objects.create(
            aryza_reference=REF, uploaded_file="credit_reports/2026/11/r.pdf", agency="Experian",
            extraction_status="extracted", extracted_data=data)
        CreditReport.objects.filter(pk=report.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago))
        return report

    def setUp(self):
        # The NEWEST report prints no CCJ; the other prints one; an OLD search
        # (not shown by CAT) prints a judgment the case has moved on from.
        self.old = self._report(_data([CCJ_500]), 600)
        self.search = self._report(_data([CCJ_283]), 20)
        self.experian = self._report(_data([]), 10)

    def _case(self, ids=None):
        return {"aryza_reference": REF, "creditors": [], "credit_report_ids": ids or []}

    def test_without_ids_the_newest_alone_as_before(self):
        case = self._case()
        _enrich_from_credit_report(case)
        self.assertFalse(case["has_ccj"])

    def test_the_shown_reports_are_pooled(self):
        case = self._case([self.experian.id, self.search.id])
        _enrich_from_credit_report(case)
        info = case["credit_report_public_information"]
        self.assertTrue(case["has_ccj"])
        self.assertEqual(["N9KF602H"], [c["case_number"] for c in info["ccjs"]],
                         "the old search CAT does not show is never brought back")

    def test_one_shown_report_is_as_before(self):
        case = self._case([self.experian.id])
        _enrich_from_credit_report(case)
        self.assertFalse(case["has_ccj"])
