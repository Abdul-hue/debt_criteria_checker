"""
AssessCaseView CHECK 2 - county routing (2026-10-21).

CHECK 2 used fuzz.partial_ratio >= 85 against every CountyCouncilRouting
county. rapidfuzz scores a partial overlap at the string edge, so "Kent"
against the "ent" ending "Civil Enforcement" scored 85.7, and a name shorter
than a county was searched inside it ("E" -> Essex, 100). 228 Aryza names that
are not councils were renamed to a county and retyped council_tax - their
debt then voted as every district of that county. A county now matches only
when the name says "council" and holds the county as whole words.
"""

from django.test import SimpleTestCase, TestCase

from debt_app.aryza_client import CaseData
from debt_app.criteria_engine import assess_case, detect_representatives
from debt_app.models import CouncilRule, CountyCouncilRouting, CreditorCriteria
from debt_app.views.criteria_views import AssessCaseView, _match_county_council

COUNTIES = ["Kent", "Cumbria", "Essex", "East Sussex", "West Sussex", "Surrey", "Derbyshire",
            "North Yorkshire", "Yorkshire (East Riding)", "Kent", "Essex"]  # one row per district

NOT_COUNCILS = [
    "Civil Enforcement", "Cabot Financial (Europe) Ltd @ Watch Portfolio Management", "DWP Overpayment",
    "Lloyds Bank Plc (Business) c/o Zinc Credit Management", "Kent Reliance", "University of Kent",
    "Kensington Mortgages", "Cambrian Credit Union Limited", "Northumbrian Water Limited", "E", "ss",
    "Essex & Suffolk Water Limited", "West Sussex & Surrey Credit Union Limited",
    "Sheffield Credit Union Ltd t/a South Yorkshire Community Bank", "Northumbria County Court",
]


class MatchCountyCouncilTests(SimpleTestCase):

    def test_genuine_county_councils_match(self):
        for name, county in (
            ("Kent County Council", "Kent"),
            ("East Sussex County Council", "East Sussex"),
            ("West Sussex County Council", "West Sussex"),
            ("Essex County Council (PCN North)", "Essex"),
            ("Cumbria County Council", "Cumbria"),
        ):
            with self.subTest(name=name):
                self.assertEqual(_match_county_council(name, COUNTIES), county)

    def test_case_is_ignored(self):
        self.assertEqual(_match_county_council("KENT COUNTY COUNCIL", COUNTIES), "Kent")
        self.assertEqual(_match_county_council("east sussex county council", COUNTIES), "East Sussex")

    def test_longest_county_wins(self):
        self.assertEqual(_match_county_council("North Yorkshire County Council", COUNTIES), "North Yorkshire")

    def test_names_that_are_not_councils_never_match(self):
        for name in NOT_COUNCILS:
            with self.subTest(name=name):
                self.assertIsNone(_match_county_council(name, COUNTIES))

    def test_county_must_be_a_whole_word(self):
        # "council" present, but the county only appears inside other words.
        self.assertIsNone(_match_county_council("Kentish Town Council", COUNTIES))
        self.assertIsNone(_match_county_council("Essexford Parish Council", COUNTIES))


def _case(name, debt_type="unsecured"):
    case = CaseData()
    case.aryza_reference = "TEST-CHECK2"
    case.client_name = "Test Client"
    case.creditors = [
        {"name": "Barclaycard", "type": "credit_card", "balance": 500000, "ref": "B1"},
        {"name": name, "type": debt_type, "balance": 300000, "ref": "T1"},
    ]
    case.income = {"total": 150000}
    case.expenditure = {"total": 120000}
    return case


class PrepareEnginePayloadCheck2Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        CountyCouncilRouting.objects.all().delete()
        CouncilRule.objects.all().delete()
        CreditorCriteria.objects.all().delete()
        cls.ashford = CouncilRule.objects.create(council_name="Ashford Borough Council", status="WILL_CONSIDER")
        CouncilRule.objects.create(council_name="Zzyborough District Council", status="REJECT")
        for county, district in (("Kent", "Ashford BC"), ("Kent", "Swale BC"), ("Cumbria", "Carlisle CC"),
                                 ("Essex", "Basildon BC"), ("East Sussex", "Lewes DC"), ("Surrey", "Woking BC"),
                                 ("Derbyshire", "Erewash BC"), ("North Yorkshire", "Selby")):
            CountyCouncilRouting.objects.create(county_name=county, district_name=district,
                                                council_rule=cls.ashford if district == "Ashford BC" else None)
        for name, rep, status in (
            ("Barclaycard", "NONE", "ACCEPT"),
            ("DWP", "NONE", "DO_NOT_VOTE"),
            ("Cabot Financial", "WATCH", "ACCEPT"),
            ("Lloyds", "NONE", "ACCEPT"),
            ("West Sussex and Surrey Credit Union", "NONE", "REJECT"),
            ("Erewash Credit Union", "NONE", "REJECT"),
            ("East Sussex Credit Union", "NONE", "REJECT"),
            ("CAMBRIAN Credit Union", "NONE", "WILL_CONSIDER"),
            ("Sheffield Credit Union", "NONE", "ACCEPT"),
        ):
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status, is_active=True)

    def _prepared(self, name, debt_type="unsecured"):
        _payload, prepared, _ = AssessCaseView()._prepare_engine_payload(_case(name, debt_type))
        return next(c for c in prepared if c["original_name"] == name)

    def _assess(self, name):
        payload, _prepared, _ = AssessCaseView()._prepare_engine_payload(_case(name))
        return assess_case(payload, detect_representatives(payload["creditors"]))

    def test_genuine_county_council_still_routes_to_its_districts(self):
        cr = self._prepared("Kent County Council", "council_tax")
        self.assertEqual((cr["creditor_name"], cr["creditor_type"], cr["debt_type_normalised"]),
                         ("Kent", "council_tax", "council_tax"))
        result = self._assess("Kent County Council")
        self.assertIn("Ashford Borough Council", [cp["council_name"] for cp in result["council_positions"]])

    def test_lower_case_county_council_routes_too(self):
        self.assertEqual(self._prepared("kent county council")["creditor_name"], "Kent")

    def test_non_councils_keep_their_name_and_type(self):
        for name in ("Civil Enforcement", "Kent Reliance", "University of Kent", "Cambrian Credit Union Limited",
                     "Northumbrian Water Limited", "E", "ss"):
            with self.subTest(name=name):
                cr = self._prepared(name)
                self.assertNotIn(cr["creditor_name"], {"Kent", "Cumbria", "Essex", "East Sussex"})
                self.assertEqual(cr["creditor_type"], "unsecured")

    def test_check1_council_rule_match_is_unchanged(self):
        cr = self._prepared("Zzyborough District Council")
        self.assertEqual((cr["creditor_name"], cr["creditor_type"]), ("Zzyborough District Council", "council_tax"))

    def test_creditors_hit_by_the_old_check_reach_their_own_rows(self):
        for name, row, status in (
            ("DWP Overpayment", "DWP", "DO_NOT_VOTE"),
            ("Cabot Financial (Europe) Ltd @ Watch Portfolio Management", "Cabot Financial", None),
            ("Lloyds Bank Plc (Business) c/o Zinc Credit Management", "Lloyds", "ACCEPT"),
            ("West Sussex & Surrey Credit Union Limited", "West Sussex and Surrey Credit Union", "REJECT"),
            ("Derbyshire Community Bank t/as Erewash Credit Union", "Erewash Credit Union", "REJECT"),
            ("East Sussex Credit Union Ltd t/a Wave Community Bank", "East Sussex Credit Union", "REJECT"),
            ("Cambrian Credit Union Limited", "CAMBRIAN Credit Union", "WILL_CONSIDER"),
            ("Sheffield Credit Union Ltd t/a South Yorkshire Community Bank", "Sheffield Credit Union", "ACCEPT"),
        ):
            with self.subTest(name=name):
                result = self._assess(name)
                [pos] = [p for p in result["creditor_positions"] if p.get("_creditor_idx") == 1]
                self.assertEqual(pos["resolved_canonical_name"], row)
                if pos["representative"] == "NONE":  # a WATCH row votes as its body decides
                    self.assertEqual(pos["effective_status"], status)
                self.assertEqual(result["council_positions"], [], "no manufactured district votes")

    def test_cabot_brings_watch_rules_into_play(self):
        _payload, prepared, _ = AssessCaseView()._prepare_engine_payload(
            _case("Cabot Financial (Europe) Ltd @ Watch Portfolio Management"))
        self.assertIn("WATCH", detect_representatives(prepared))
