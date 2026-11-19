"""One judgment printed more than once is one judgment (2026-11-19).

CAT case 436961: an Experian report printed one CCJ three times -- the same
court order number, date, court and £475 -- beside a second, different CCJ of
£1,852. Each copy became its own record: `ccj_count` 4 instead of 2,
`ccj_total_pence` £3,277 instead of £2,327, and CAT raised two
"CCJ (Undeclared) £475" debts that do not exist.

`credit_report.unique_judgments` keeps one copy of a PROVEN repeat only, on
both readers: the PDF text (`extract_public_information`) and the Experian
database (`experian_mapper._public_information`).
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from debt_app.integrations.credit_report import extract_public_information, unique_judgments
from debt_app.integrations.experian_mapper import JUDGEMENT_GROUP, _public_information


def _experian_record(date, amount, court, order_number):
    """One printed Experian judgment, laid out as the production reports print it
    (`tests_phase1_ccj_aoe.py`: EXPERIAN_WITH_CCJ + EXPERIAN_COURT_TAIL)."""
    return f"""Applicant - Current Address
• Date: {date}
• Type: Judgement - Judgement
• Amount: {amount}
• Settled: N
• Source: REGISTRY TRUST LTD
• Court Name: {court}
• Court Plaintif Number: NCCMCC
• Court Order Number: {order_number}
• House Match: Exact Match
"""


# The 436961 shape: the £1,852 judgment once, the £475 judgment three times.
CASE_436961 = ("Public Information\n• Number: 4\n"
               + _experian_record("20-03-2023", "1852.0", "K8BX630K", "2103396951")
               + _experian_record("18-10-2021", "475.0", "H3CD4H1R", "1910197369")
               + _experian_record("18-10-2021", "475.0", "H3CD4H1R", "1910197369")
               + _experian_record("18-10-2021", "475.0", "H3CD4H1R", "1910197369"))


def _ccj(amount_pence, date, case_number=None, court_name=None):
    return {"amount_pence": amount_pence, "settled": None, "date": date,
            "case_number": case_number, "court_name": court_name}


class PdfReaderTests(SimpleTestCase):

    def test_one_judgment_printed_three_times_is_one(self):
        info = extract_public_information(CASE_436961)
        self.assertEqual(2, info["ccj_count"])
        self.assertEqual(185200 + 47500, info["ccj_total_pence"])
        self.assertEqual(["2103396951", "1910197369"], [c["case_number"] for c in info["ccjs"]])

    def test_two_judgments_of_the_same_amount_stay_two(self):
        text = ("Public Information\n"
                + _experian_record("18-10-2021", "475.0", "H3CD4H1R", "1910197369")
                + _experian_record("18-10-2021", "475.0", "H3CD4H1R", "1910197370"))
        self.assertEqual(2, extract_public_information(text)["ccj_count"])


class TheRuleTests(SimpleTestCase):

    def test_same_number_amount_and_date_is_a_copy(self):
        kept = unique_judgments([_ccj(47500, "18-10-2021", "1910197369"),
                                 _ccj(47500, "18-10-2021", " 1910197369 ")])
        self.assertEqual(1, len(kept))

    def test_same_number_but_another_amount_is_kept(self):
        kept = unique_judgments([_ccj(47500, "18-10-2021", "1910197369"),
                                 _ccj(50000, "18-10-2021", "1910197369")])
        self.assertEqual(2, len(kept))

    def test_no_number_needs_the_same_court_amount_and_date(self):
        same = [_ccj(47500, "18-10-2021", court_name="H3CD4H1R"),
                _ccj(47500, "18-10-2021", court_name="h3cd4h1r")]
        other_court = [_ccj(47500, "18-10-2021", court_name="H3CD4H1R"),
                       _ccj(47500, "18-10-2021", court_name="K8BX630K")]
        self.assertEqual(1, len(unique_judgments(same)))
        self.assertEqual(2, len(unique_judgments(other_court)))

    def test_a_record_too_bare_to_identify_is_always_kept(self):
        bare = [_ccj(47500, "18-10-2021"), _ccj(47500, "18-10-2021"),
                _ccj(None, "18-10-2021", "1910197369"), _ccj(None, "18-10-2021", "1910197369")]
        self.assertEqual(4, len(unique_judgments(bare)))

    def test_the_first_copy_is_kept_in_order(self):
        first = _ccj(47500, "18-10-2021", "1910197369")
        kept = unique_judgments([_ccj(185200, "20-03-2023", "2103396951"), first,
                                 _ccj(47500, "18-10-2021", "1910197369")])
        self.assertIs(first, kept[1])
        self.assertEqual(2, len(kept))


class ExperianDatabaseReaderTests(SimpleTestCase):
    """The same judgment under each matched address in the search's JSON."""

    def test_one_judgment_under_three_addresses_is_one(self):
        def block(amount, date, number):
            return {"PublicInfoDetails": [{"InformationType": "JG", "AmountPounds": amount,
                                           "AmountPence": 0, "InformationDate": date,
                                           "CameraNumber": number}]}
        consumer = {"PublicInformation": [block("1852", "2023-03-20", "2103396951"),
                                          block("475", "2021-10-18", "1910197369"),
                                          block("475", "2021-10-18", "1910197369"),
                                          block("475", "2021-10-18", "1910197369")]}
        tables = SimpleNamespace(public_info_types={"JG": JUDGEMENT_GROUP})
        info = _public_information(consumer, {"SummaryFlags": {"DebtManagement": "N"}}, tables)
        self.assertEqual(2, info["ccj_count"])
        self.assertEqual(185200 + 47500, info["ccj_total_pence"])
