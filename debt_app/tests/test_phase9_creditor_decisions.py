"""
Phase 9 (manager, 2026-10-21): final creditor business requirements.

1. Parkingeye Limited (05134454): DO NOT VOTE - including its parking-ticket
   debts, which used to bypass the creditor lookup. Council PCNs keep their
   council rules; "Car Parking Partnership (CPP)" (02920033) is another company.
2. Quidie Limited t/a Fernovo (08110266): DO NOT VOTE. Not Quick Quid, not
   Quidmarket.
3. Propel Holdings UK / Stagemount t/a Quidmarket (07259223): TIX - the vote
   comes from the TIX rules like every TIX row. Not Quidie, not Quick Quid.
4. South Manchester Credit Union: REJECT, a separate lender.
5. Manchester Credit Union: REJECT if the loan is under 3 months old (the
   existing credit-report loan-age rule); otherwise its own status.
6. "X c/o Y" (option b): the treatment follows Y when Y has an exact row;
   otherwise the name resolves as it did before.

The Phase 9 rows come from migration 0091; the comparison rows (Quick Quid,
Wilkin Chapman, ...) are created here.
"""
from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import _resolve_creditor_criteria, assess_case, detect_representatives
from debt_app.helpers import (
    _get_creditor_by_trading_name_uncached, care_of_organisation, get_creditor_by_exact_name,
)
from debt_app.models import CouncilRule, CreditorCriteria

PARKINGEYE = "Parkingeye Limited"
QUIDIE = "Quidie Limited t/a Fernovo"
QUIDMARKET = "Propel Holdings UK T/A Quidmarket"


def _resolved(name):
    """The row name the engine assesses `name` against (alias hop + resolver), or None."""
    try:
        return _resolve_creditor_criteria(name).creditor_name
    except CreditorCriteria.DoesNotExist:
        return None


def _payload(creditors):
    return {
        "creditors": [
            {"name": n, "creditor_type": t, "balance": b, **extra} for n, t, b, *rest in creditors
            for extra in [rest[0] if rest else {}]
        ],
        "financial_summary": {"net_balance": 300},
        "documents": [], "gold_transactions": [], "evidence_ledger": [],
    }


def _position(result, name):
    """The creditor position for an Aryza name (positions carry the resolved name)."""
    return next(p for p in result["creditor_positions"]
                if name in (p.get("creditor_name"), p.get("display_name"), p.get("original_aryza_name")))


class Phase9Data(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, rep, status in (
            ("Quick Quid", "NONE", "DO_NOT_VOTE"),
            ("Barclaycard", "NONE", "ACCEPT"),
            ("LINK", "NONE", "WILL_CONSIDER"),
            ("Wilkin Chapman", "NONE", "REJECT"),
            ("Blues and Twos credit union", "NONE", "REJECT"),
            ("American Express", "NONE", "WILL_CONSIDER"),
            ("Brachers LLP", "NONE", "WILL_CONSIDER"),
            ("Opus", "WATCH", "ACCEPT"),
            ("Asset Link Capital", "WATCH", "ACCEPT"),
            ("Lowell", "TIX", "ACCEPT"),
        ):
            CreditorCriteria.objects.get_or_create(
                creditor_name=name, defaults={"representative": rep, "status": status, "is_active": True},
            )
        CouncilRule.objects.get_or_create(council_name="Zzyborough District Council", defaults={"status": "WILL_CONSIDER"})


class MigrationRowsTests(Phase9Data):
    def test_rows_and_treatments(self):
        rows = {r.creditor_name: r for r in CreditorCriteria.objects.filter(creditor_name__in=[
            PARKINGEYE, QUIDIE, QUIDMARKET, "South Manchester Credit Union", "Manchester Credit Union"])}
        self.assertEqual(("NONE", "DO_NOT_VOTE"), (rows[PARKINGEYE].representative, rows[PARKINGEYE].status))
        self.assertEqual(("NONE", "DO_NOT_VOTE"), (rows[QUIDIE].representative, rows[QUIDIE].status))
        self.assertEqual("TIX", rows[QUIDMARKET].representative)
        self.assertEqual("REJECT", rows["South Manchester Credit Union"].status)
        mcu = rows["Manchester Credit Union"]
        self.assertEqual(("WILL_CONSIDER", 3), (mcu.status, mcu.account_age_months))


class ParkingeyeTests(Phase9Data):
    def test_confirmed_names_reach_the_parkingeye_row(self):
        for name in ("Parkingeye Limited", "ParkingEye Ltd T/as Car Parking Partnership", "Parking Eye",
                     "Parking Eye Ltd", "Parking Eye LTD (CCBC)"):
            self.assertEqual(PARKINGEYE, _resolved(name), name)

    def test_car_parking_partnership_cpp_is_not_parkingeye(self):
        # "Car Parking Partnership (CPP)" is company 02920033; the plain name
        # normalises to the same key, so neither is mapped.
        for name in ("Car Parking Partnership (CPP)", "Car Parking Partnership", "Car Parking Partnership Ltd"):
            self.assertIsNone(_resolved(name), name)

    def test_parking_ticket_debt_is_do_not_vote(self):
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0),
                                       ("Parkingeye Limited", "parking_ticket", 300.0)]), detected_representatives=set())
        pos = _position(result, "Parkingeye Limited")
        self.assertEqual("DO_NOT_VOTE", pos["effective_status"])
        self.assertNotIn("PCN-NO-COUNCIL-RULE", pos["rule_ids"] or [])
        self.assertNotIn("Parkingeye Limited", [u["name"] for u in result["majority_analysis"]["unknown_creditors"]])

    def test_other_debt_types_are_do_not_vote_too(self):
        for debt_type in ("loan", "unsecured_ccj", ""):
            result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0),
                                           ("Parking Eye", debt_type, 300.0)]), detected_representatives=set())
            self.assertEqual("DO_NOT_VOTE", _position(result, "Parking Eye")["effective_status"], debt_type)

    def test_council_pcn_keeps_its_council_rule(self):
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0),
                                       ("Parkingeye Limited", "parking_ticket", 300.0),
                                       ("Zzyborough District Council", "parking_ticket", 400.0)]),
                             detected_representatives=set())
        [cp] = [cp for cp in result["council_positions"] if cp["council_name"] == "Zzyborough District Council"]
        self.assertEqual("WILL_CONSIDER", cp["effective_status"])
        self.assertNotIn("Parkingeye Limited", [cp["council_name"] for cp in result["council_positions"]])

    def test_other_private_parking_stays_unknown_and_never_partial_matches(self):
        # "Link Parking Ltd" would reach LINK by the whole-word step; a parking
        # debt only uses a creditor row on an exact name.
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0),
                                       ("Link Parking Ltd", "parking_ticket", 300.0),
                                       ("Car Parking Partnership (CPP)", "parking_ticket", 200.0)]),
                             detected_representatives=set())
        for name in ("Link Parking Ltd", "Car Parking Partnership (CPP)"):
            pos = _position(result, name)
            self.assertEqual(("UNKNOWN", ["PCN-NO-COUNCIL-RULE"]), (pos["effective_status"], pos["rule_ids"]), name)


class QuidieTests(Phase9Data):
    def test_quidie_and_fernovo_names_are_do_not_vote(self):
        for name in ("Quidie Limited t/a Fernovo", "Quidie Ltd", "Quidie Limited", "Quidie", "Fernovo",
                     "Quidie Limited (Fernovo)", "Quidie Limited trading as Fernovo"):
            self.assertEqual(QUIDIE, _resolved(name), name)
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0), ("Fernovo", "loan", 400.0)]),
                             detected_representatives=set())
        self.assertEqual("DO_NOT_VOTE", _position(result, "Fernovo")["effective_status"])

    def test_quidie_is_not_quick_quid_or_quidmarket(self):
        self.assertEqual("Quick Quid", _resolved("Quick Quid (IN ADMINISTRATION)"))
        for name in ("Quidie Ltd", "Fernovo"):
            self.assertNotIn(_resolved(name), ("Quick Quid", QUIDMARKET))

    def test_unconfirmed_quidieloan_is_not_mapped(self):
        self.assertIsNone(_resolved("Quidieloan"))


class QuidmarketTests(Phase9Data):
    NAMES = ("Propel Holdings UK T/A Quidmarket", "Propel Holdings UK T/A Quidmarket (POST 23/04/26)",
             "Stagemount Limited t/a Quidmarket", "Stagemount T/As Quidmarket", "Stagemount Limited",
             "Stagemount Ltd (I)", "QuidMarket Loans", "Quidmarket", "Quid Market")

    def test_confirmed_variants_reach_the_tix_row(self):
        for name in self.NAMES:
            self.assertEqual(QUIDMARKET, _resolved(name), name)

    def test_tix_body_decides_the_vote(self):
        self.assertEqual({"TIX"}, detect_representatives([{"name": "Stagemount Limited t/a Quidmarket", "balance": 500.0}]))
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0),
                                       ("Stagemount Limited t/a Quidmarket", "loan", 500.0)]))
        pos = _position(result, "Stagemount Limited t/a Quidmarket")
        self.assertEqual("TIX", pos["representative"])
        self.assertNotEqual("PENDING_REP_OUTCOME", pos["effective_status"])
        self.assertEqual(result["representative_outcomes"]["TIX"]["status"], pos["effective_status"])

    def test_not_quidie_quick_quid_or_propel_finance(self):
        for name in self.NAMES:
            self.assertNotIn(_resolved(name), (QUIDIE, "Quick Quid"))
        self.assertIsNone(_resolved("Propel Finance Plc"))


class CreditUnionTests(Phase9Data):
    def _status(self, name, **creditor):
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0), (name, "loan", 800.0, creditor)]),
                             detected_representatives=set())
        return _position(result, name)

    def test_south_manchester_rejects(self):
        for name in ("South Manchester Credit Union", "South Manchester Credit Union Limited"):
            self.assertEqual("South Manchester Credit Union", _resolved(name), name)
            self.assertEqual("REJECT", self._status(name)["effective_status"], name)

    def test_manchester_rejects_a_loan_under_3_months(self):
        pos = self._status("Manchester Credit Union", account_age_months=2)
        self.assertEqual("REJECT", pos["effective_status"])
        self.assertIn("CREDITOR-LOAN-TOO-RECENT-REJECT", [f["code"] for f in pos["findings"]])

    def test_manchester_keeps_its_own_status_otherwise(self):
        self.assertEqual("WILL_CONSIDER", self._status("Manchester Credit Union", account_age_months=3)["effective_status"])
        self.assertEqual("WILL_CONSIDER", self._status("Manchester Credit Union Ltd", account_age_months=24)["effective_status"])
        unknown_age = self._status("Manchester Credit Union")
        self.assertEqual("WILL_CONSIDER", unknown_age["effective_status"])
        self.assertIn("CREDITOR-LOAN-AGE-UNVERIFIED", [f["code"] for f in unknown_age["findings"]])

    def test_the_two_lenders_stay_separate(self):
        self.assertEqual("Manchester Credit Union", _resolved("Manchester Credit Union Ltd"))
        self.assertEqual("South Manchester Credit Union", _resolved("South Manchester Credit Union Limited"))


class CareOfTests(Phase9Data):
    def test_known_organisation_after_co_decides(self):
        self.assertEqual("Wilkin Chapman", _resolved("Blues & Twos Credit Union Limited c/o Wilkin Chapman LLP"))
        self.assertEqual("Brachers LLP", _resolved("American Express Services Europe Ltd c/o Brachers"))

    def test_organisation_with_no_treatment_keeps_the_existing_resolution(self):
        # Option b: no exact row for the organisation after c/o -> resolved as before.
        self.assertEqual("American Express",
                         _resolved("American Express Services Europe Ltd c/o Unheard Of Collections Ltd"))
        self.assertEqual("Lowell", _resolved("Lowell Portfolio c/o Unheard Of Collections Ltd"))

    def test_similar_looking_organisation_is_not_an_exact_match(self):
        # "Wilkin Chapman Rollits LLP" is not the 'Wilkin Chapman' row and "Opus
        # Restructuring" is not 'Opus': the c/o step never decides on them, so
        # the name keeps the resolution it had (Lowell's TIX here).
        self.assertIsNone(get_creditor_by_exact_name("Wilkin Chapman Rollits LLP"))
        self.assertIsNone(get_creditor_by_exact_name("Opus Restructuring Llp"))
        self.assertEqual("Lowell", _resolved("Lowell Portfolio c/o Wilkin Chapman Rollits LLP"))

    def test_explicit_whole_name_mappings_still_win(self):
        self.assertEqual("Asset Link Capital", _resolved("Asset Link Capital c/o The Insolvency Exchange"))
        self.assertEqual(QUIDMARKET, _resolved("QuidMarket Loans c/o The Insolvency Exchange"))

    def test_names_without_co_are_unchanged(self):
        self.assertEqual("Barclaycard", _get_creditor_by_trading_name_uncached("Barclaycard Plc").creditor_name)

    def test_assessed_vote_follows_the_organisation_after_co(self):
        name = "Blues & Twos Credit Union Limited c/o Wilkin Chapman LLP"
        result = assess_case(_payload([("Barclaycard", "credit_card", 5000.0), (name, "loan", 800.0)]),
                             detected_representatives=set())
        self.assertEqual("REJECT", _position(result, name)["effective_status"])


class CareOfParsingTests(SimpleTestCase):
    def test_the_organisation_after_the_last_co(self):
        self.assertEqual("Wilkin Chapman", care_of_organisation("NHS Trust c/o c/o Wilkin Chapman"))
        self.assertEqual("Opus Restructuring Llp", care_of_organisation("PR Potential C/O Opus Restructuring Llp"))
        self.assertEqual("WPM (Intrum)", care_of_organisation("Tesco C/O WPM (Intrum)"))

    def test_no_co(self):
        for name in ("Barclaycard", "Fabric/Other Ltd", "Disco/Ops", "X c/o", ""):
            self.assertIsNone(care_of_organisation(name), name)
