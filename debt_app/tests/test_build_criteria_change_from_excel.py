"""
build_criteria_change_from_excel: proposals from the markdown + recorded
decisions, grouped into DRAFT change requests through the existing service.

Covers: field-level before/after, manual-edit flags, representative-body rows
skipped, structured changes (Admiral, Loans by Mal; Match the Cash keeps 50p), rename
aliases, council duplicates (Suffolk Coastal resolved, Wycombe left alone),
dividends, Evolve retirement, rule switches (incl. already-off rules), the
separate HMRC draft, dry-run writes nothing, drafts only (no version, live
rows untouched), idempotent re-runs, and replacement of a stale draft.
"""

import io
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from debt_app.models import CouncilRule, CreditorCriteria, CriteriaChangeRequest, CriteriaVersion, GlobalCriteria
from debt_app.services import criteria_change_builder as b

GENERAL = """# GENERAL CREDITOR

| Creditor | Accept / Reject | Notes / Criteria | updated criteria | Phone Number | Email | Contact |
| --- | --- | --- | --- | --- | --- | --- |
| Bamboo | Will Consider | notes |  |  |  |  |
| Everyday Loans | REJECT |  |  |  |  |  |
| Octopus Energy | Accept |  |  |  |  |  |
| Watchy Bank | REJECT | rep creditor, status ignored |  |  |  |  |
| Startline Motor Finance | DO NOT VOTE | Sheet says: 'can get a vote if chased'. |  |  |  |  |
| Odd Status Co | TRADING STYLE OF AMIGO |  |  |  |  |  |
| Not In Db Ltd | Accept |  |  |  |  |  |
| Admiral Loans | Will Consider | running cases: 6 months or older |  |  |  |  |
| Loans by Mal | Will Consider | 40p if 3-6 months |  |  |  |  |
| Match the Cash t/a Guarantor My Loan (Match the Cash trading name) | Will consider |  |  |  |  |  |
| Clevr Money (Blackpool, Fylde & Wyre Credit Union Ltd) | REJECT |  |  |  |  |  |
"""

COUNCILS = """# Councils

| # | Council | Status | Notes | Updated Criteria | Criteria Changed From Rej Date | Contact Name | Contact Number |
|---|---------|--------|-------|------------------|-------------------------------|--------------|----------------|
| 1 | Basildon Borough Council | REJECT | flat rejection |  |  |  |  |
| 2 | Suffolk Coastal District Council | Will Consider | Will consider council tax. |  |  |  |  |
| 3 | Suffolk Coastal District Council | Reject | will not consider any IVA confirmed 13/10/2021 | 31.07.26 |  |  |  |
| 4 | Wycombe District Council | Will Consider |  |  |  |  |  |
| 5 | Wycombe District Council | Accept | 50P/£ MINIMUM DIV |  |  |  |  |
| 6 | Blank Status Council |  | no stance given |  |  |  |  |
| 7 | Oxford City Council | REJECT | new council |  |  |  |  |
| 8 | Some Credit Union | REJECT | not a council |  |  |  |  |
| 9 | Liney Borough Council was abolished.   Now Elsewhere Council | Reject | now rejects |  |  |  |  |
"""

DIVIDENDS = """# Dividends

| Creditor | Div Required | Notes |
| --- | --- | --- |
| Amigo |  | DO NOT REQUIRE A DIV NOW |
| Guarantor My Loan | 100P/£ |  |
| Ratesetter | 25p | if under 6 months old it 50p |
"""

WHICH_REP = """# Which Representative

## (WATCH) WPM
- Watchy Bank
- Scottish Power

## TIX
- Tixy Finance
"""


class BuilderTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "Excel Criteria"
        self.dir.mkdir()
        (self.dir / "General_Creditors.md").write_text(GENERAL, encoding="utf-8")
        (self.dir / "Councils.md").write_text(COUNCILS, encoding="utf-8")
        (self.dir / "Dividends_Criteria.md").write_text(DIVIDENDS, encoding="utf-8")
        (self.dir / "Which_Representative_Criteria.md").write_text(WHICH_REP, encoding="utf-8")

        self.admin = User.objects.create_user("admin", is_staff=True)
        self.author = User.objects.create_user("author")

        # The test database already holds the creditors, councils and rules the
        # migrations seed, so set exact values rather than create blindly.
        def cred(name, **kw):
            kw.setdefault("representative", "NONE")
            kw.setdefault("status", "ACCEPT")
            kw.setdefault("updated_by", None)
            kw.setdefault("trading_names", [])
            kw.setdefault("account_age_months", None)
            kw.setdefault("min_dividend_pence", None)
            kw.setdefault("reject_if_second_iva", False)
            kw.setdefault("young_account_months", None)
            kw.setdefault("young_account_min_dividend_pence", None)
            kw.setdefault("is_active", True)
            obj, _ = CreditorCriteria.objects.update_or_create(creditor_name=name, defaults=kw)
            return obj

        def council(name, status):
            obj, _ = CouncilRule.objects.update_or_create(council_name=name, defaults={"status": status})
            return obj

        self.bamboo = cred("Bamboo", status="REJECT")
        self.everyday = cred("Everyday Loans", status="WILL_CONSIDER")
        self.octopus = cred("Octopus Energy", representative="EVOLVE", status="ACCEPT", updated_by=self.admin)
        self.shell = cred("Shell Energy", representative="EVOLVE", status="ACCEPT")
        self.shell_dup = cred("Shell Energy Retail Limited (NOW OCTOPUS)", status="ACCEPT")
        self.mint = cred("Mint", representative="EVOLVE", status="ACCEPT")
        self.barclaycard = cred("Barclaycard", representative="EVOLVE", status="ACCEPT")
        self.hmrc = cred("HM Revenue & Customs", status="WILL_CONSIDER", reject_if_equity_exceeds_debt=True)
        self.watchy = cred("Watchy Bank", representative="WATCH", status="ACCEPT")
        self.startline = cred("Startline Motor Finance", status="DO_NOT_VOTE")
        self.odd = cred("Odd Status Co", status="WILL_CONSIDER")
        self.admiral = cred("Admiral Loans", status="WILL_CONSIDER", account_age_months=3)
        self.mal = cred("Loans by Mal", status="WILL_CONSIDER", account_age_months=3)
        self.match = cred("Match the Cash t/a Guarantor My Loan (Match the Cash trading name)", status="WILL_CONSIDER", min_dividend_pence=50)
        self.guarantor = cred("Guarantor My Loan", min_dividend_pence=50)
        self.ratesetter = cred("Ratesetter", min_dividend_pence=50, account_age_months=6)
        self.clever = cred("Clever Money (Blackpool, Fylde & Wyre Credit Union Ltd)", status="REJECT")
        self.scottish = cred("Scottish Power", status="DO_NOT_VOTE")
        self.tixy = cred("Tixy Finance", representative="TIX")

        council("Basildon Borough Council", "DO_NOT_VOTE")
        # a row created straight from the workbook, with line breaks in the name
        self.liney = council("Liney Borough Council was abolished.\n\n\nNow Elsewhere Council", "DO_NOT_VOTE")
        self.suffolk = council("Suffolk Coastal District Council", "WILL_CONSIDER")
        council("Wycombe District Council", "ACCEPT")
        council("Blank Status Council", "ACCEPT")
        CouncilRule.objects.filter(council_name__iexact="Oxford City Council").delete()

        for key, active in (("WATCH-22.3", False), ("WATCH-22.4", True), ("WATCH-22.6", True),
                            ("EVOLVE-01", True), ("EVOLVE-02", True), ("EVOLVE-03", True), ("TIG-15.4", False)):
            GlobalCriteria.objects.update_or_create(
                rule_key=key,
                defaults={"criteria_set": key.split("-")[0], "rule_name": key, "severity": "hard_block", "is_active": active},
            )

    def tearDown(self):
        self._tmp.cleanup()

    def _proposals(self):
        ps = b.build_proposals(str(self.dir))
        flat = {(p["model"], p["object_id"], p["field"]): p for g in ps.groups.values() for p in g}
        return ps, flat

    # ------------------------------------------------------------- proposals

    def test_creditor_statuses(self):
        ps, flat = self._proposals()
        p = flat[("CreditorCriteria", self.bamboo.pk, "status")]
        self.assertEqual((p["old_value"], p["new_value"]), ("REJECT", "WILL_CONSIDER"))
        self.assertIn("Sheet says 'Will Consider'", p["rationale"])
        self.assertEqual(flat[("CreditorCriteria", self.everyday.pk, "status")]["new_value"], "REJECT")
        # representative-body creditor: status is not used, so not proposed
        self.assertNotIn(("CreditorCriteria", self.watchy.pk, "status"), flat)
        self.assertTrue(any("Watchy Bank" in n and "represented by WATCH" in n for n in ps.notes))
        # unchanged, unrecognised and missing rows
        self.assertNotIn(("CreditorCriteria", self.startline.pk, "status"), flat)
        self.assertTrue(any("Odd Status Co" in n and "not a recognised stance" in n for n in ps.notes))
        self.assertTrue(any("Not In Db Ltd" in n and "notes-only sync" in n for n in ps.notes))
        # every proposal in group 1 lands in group 1
        self.assertIn(p, ps.groups["creditor_statuses"])

    def test_structured_changes_and_rename_alias(self):
        ps, flat = self._proposals()
        self.assertEqual(flat[("CreditorCriteria", self.admiral.pk, "account_age_months")]["new_value"], 6)
        self.assertEqual(flat[("CreditorCriteria", self.admiral.pk, "reject_if_second_iva")]["new_value"], True)
        self.assertEqual(flat[("CreditorCriteria", self.mal.pk, "young_account_months")]["new_value"], 6)
        self.assertEqual(flat[("CreditorCriteria", self.mal.pk, "young_account_min_dividend_pence")]["new_value"], 40)
        # Match the Cash keeps its own row's 50p; the Dividends sheet's 100p is
        # Guarantor My Loan's (separate row), not inherited.
        self.assertNotIn(("CreditorCriteria", self.match.pk, "min_dividend_pence"), flat)
        alias = flat[("CreditorCriteria", self.clever.pk, "trading_names")]
        self.assertEqual(alias["new_value"], ["Clever Money (Blackpool, Fylde & Wyre Credit Union Ltd)"])
        self.assertEqual(CreditorCriteria.objects.filter(creditor_name__icontains="Blackpool").count(), 1)

    def test_council_statuses_and_duplicates(self):
        ps, flat = self._proposals()
        basildon = CouncilRule.objects.get(council_name="Basildon Borough Council")
        self.assertEqual(flat[("CouncilRule", basildon.pk, "status")]["new_value"], "REJECT")
        suffolk = flat[("CouncilRule", self.suffolk.pk, "status")]
        self.assertEqual((suffolk["old_value"], suffolk["new_value"]), ("WILL_CONSIDER", "REJECT"))
        self.assertIn("take the last row", suffolk["rationale"])
        self.assertEqual(CouncilRule.objects.filter(council_name__icontains="Suffolk Coastal").count(), 1)
        wycombe = CouncilRule.objects.get(council_name="Wycombe District Council")
        self.assertNotIn(("CouncilRule", wycombe.pk, "status"), flat)
        self.assertTrue(any("Wycombe" in n and "matches one of them" in n for n in ps.notes))
        self.assertTrue(any("Blank Status Council" in n and "no status" in n for n in ps.notes))
        self.assertTrue(any("Oxford City Council" in n and "seed_all_councils" in n for n in ps.notes))
        self.assertFalse(any("Some Credit Union" in n for n in ps.notes))
        # whitespace-insensitive match: the line-broken database row is found, not reported as new
        liney = flat[("CouncilRule", self.liney.pk, "status")]
        self.assertEqual((liney["old_value"], liney["new_value"]), ("DO_NOT_VOTE", "REJECT"))
        self.assertFalse(any("Liney" in n for n in ps.notes))

    def test_dividends_representatives_and_evolve_retirement(self):
        ps, flat = self._proposals()
        g = flat[("CreditorCriteria", self.guarantor.pk, "min_dividend_pence")]
        self.assertEqual((g["old_value"], g["new_value"]), (50, 100))
        # Ratesetter's agreed two tiers: 25p standard, 50p under six months, and the
        # stand-in six-month reject cleared. All four land in the same draft.
        rs = {f: flat[("CreditorCriteria", self.ratesetter.pk, f)] for f in
              ("min_dividend_pence", "young_account_months", "young_account_min_dividend_pence", "account_age_months")}
        self.assertEqual((rs["min_dividend_pence"]["old_value"], rs["min_dividend_pence"]["new_value"]), (50, 25))
        self.assertEqual(rs["young_account_months"]["new_value"], 6)
        self.assertEqual(rs["young_account_min_dividend_pence"]["new_value"], 50)
        self.assertEqual((rs["account_age_months"]["old_value"], rs["account_age_months"]["new_value"]), (6, None))
        for p in rs.values():
            self.assertIn(p, ps.groups["dividends_representatives"])
        self.assertFalse(any("NEEDS DECISION" in n for n in ps.notes))
        self.assertEqual(flat[("CreditorCriteria", self.scottish.pk, "representative")]["new_value"], "WATCH")
        self.assertNotIn(("CreditorCriteria", self.watchy.pk, "representative"), flat)   # already WATCH
        self.assertNotIn(("CreditorCriteria", self.tixy.pk, "representative"), flat)     # already TIX
        octo = flat[("CreditorCriteria", self.octopus.pk, "representative")]
        self.assertEqual((octo["old_value"], octo["new_value"]), ("EVOLVE", "NONE"))
        self.assertEqual(octo["flags"], ["last edited by admin; review carefully"])
        # Octopus has an explicit Accept in the General sheet: its status is left alone
        self.assertNotIn(("CreditorCriteria", self.octopus.pk, "status"), flat)
        # Shell Energy: confirmed (2026-10-13) to be the sheet's "Shell Energy Retail Limited (NOW OCTOPUS)"
        # row, which says Accept -> representative NONE, status kept, names consolidated onto this record
        shell = flat[("CreditorCriteria", self.shell.pk, "representative")]
        self.assertEqual(shell["new_value"], "NONE")
        self.assertIn("user confirmed", shell["rationale"])
        self.assertNotIn(("CreditorCriteria", self.shell.pk, "status"), flat)
        self.assertEqual(CreditorCriteria.objects.get(pk=self.shell.pk).status, "ACCEPT")
        self.assertNotIn(("CreditorCriteria", self.shell.pk, "trading_names"), flat)   # already Octopus Energy's (migration 0030)
        dup = flat[("CreditorCriteria", self.shell_dup.pk, "is_active")]
        self.assertEqual((dup["old_value"], dup["new_value"]), (True, False))
        self.assertFalse(any(n.startswith("CONFIRM 'Shell Energy'") for n in ps.notes))
        # Mint: no stance of its own anywhere -> representative NONE and stance UNKNOWN, never the default Accept
        mint_rep = flat[("CreditorCriteria", self.mint.pk, "representative")]
        mint_status = flat[("CreditorCriteria", self.mint.pk, "status")]
        self.assertEqual(mint_rep["new_value"], "NONE")
        self.assertEqual((mint_status["old_value"], mint_status["new_value"]), ("ACCEPT", "UNKNOWN"))
        self.assertIn("never treats it as an acceptance", mint_status["rationale"])
        # Barclaycard: on the WATCH list -> WATCH, body rules decide, no status proposal
        bc = flat[("CreditorCriteria", self.barclaycard.pk, "representative")]
        self.assertEqual(bc["new_value"], "WATCH")
        self.assertNotIn(("CreditorCriteria", self.barclaycard.pk, "status"), flat)
        for p in (g, octo, shell, dup, mint_rep, mint_status, bc):
            self.assertIn(p, ps.groups["dividends_representatives"])

    def test_hmrc_legacy_equity_flag_is_switched_off_with_tig_15_4(self):
        ps, flat = self._proposals()
        flag = flat[("CreditorCriteria", self.hmrc.pk, "reject_if_equity_exceeds_debt")]
        self.assertEqual((flag["old_value"], flag["new_value"]), (True, False))
        self.assertIn(flag, ps.groups["hmrc_equity"])
        self.assertIn("Superseded by TIG-15.4", flag["rationale"])
        self.assertEqual(len(ps.groups["hmrc_equity"]), 2)   # TIG-15.4 on + legacy flag off, reviewed together

    def test_rule_switches_and_separate_hmrc_group(self):
        ps, flat = self._proposals()
        keys = {GlobalCriteria.objects.get(rule_key=k).pk: k for k in ("WATCH-22.4", "WATCH-22.6", "EVOLVE-01", "EVOLVE-02", "EVOLVE-03", "TIG-15.4")}
        switches = {keys[p["object_id"]]: p for p in ps.groups["rule_switches"]}
        self.assertEqual(set(switches), {"WATCH-22.4", "WATCH-22.6", "EVOLVE-01", "EVOLVE-02", "EVOLVE-03"})
        self.assertTrue(all(p["old_value"] is True and p["new_value"] is False for p in switches.values()))
        self.assertTrue(any("WATCH-22.3 is already off" in n for n in ps.notes))
        hmrc = [p for p in ps.groups["hmrc_equity"] if p["model"] == "GlobalCriteria"]
        self.assertEqual(len(hmrc), 1)
        self.assertEqual((hmrc[0]["old_value"], hmrc[0]["new_value"]), (False, True))
        self.assertIn("trial must confirm", hmrc[0]["rationale"])

    # ---------------------------------------------------------------- drafts

    def _run(self, *args):
        out = io.StringIO()
        call_command("build_criteria_change_from_excel", "--criteria-dir", str(self.dir), *args, stdout=out)
        return out.getvalue()

    def test_dry_run_prints_everything_and_writes_nothing(self):
        out = self._run("--dry-run")
        self.assertEqual(CriteriaChangeRequest.objects.count(), 0)
        self.assertIn("'Bamboo'", out)
        self.assertIn("status: 'REJECT' -> 'WILL_CONSIDER'", out)
        self.assertIn("would-create", out)
        self.assertIn("last edited by admin", out)
        self.assertIn("== Skipped / conflicts / warnings ==", out)
        self.assertIn("Dry run", out)

    def test_creates_drafts_only_and_touches_no_live_row(self):
        out = self._run("--user", "author")
        drafts = CriteriaChangeRequest.objects.order_by("pk")
        self.assertEqual(drafts.count(), 5)
        self.assertTrue(all(d.status == CriteriaChangeRequest.STATUS_DRAFT for d in drafts))
        self.assertTrue(all(d.created_by == self.author for d in drafts))
        self.assertEqual(
            [d.title for d in drafts],
            [b.draft_title(k) for k, _ in b.GROUPS],
        )
        self.assertEqual(CriteriaVersion.objects.count(), 0)
        # live data untouched
        self.assertEqual(CreditorCriteria.objects.get(pk=self.bamboo.pk).status, "REJECT")
        self.assertEqual(CouncilRule.objects.get(pk=self.suffolk.pk).status, "WILL_CONSIDER")
        self.assertTrue(GlobalCriteria.objects.get(rule_key="WATCH-22.4").is_active)
        # items carry before/after; reason carries the rationale
        d1 = drafts[0]
        item = next(i for i in d1.items if i["object_id"] == self.bamboo.pk and i["field"] == "status")
        self.assertEqual((item["old_value"], item["new_value"], item["object_label"]), ("REJECT", "WILL_CONSIDER", "Bamboo"))
        self.assertIn("'Bamboo' status: 'REJECT' -> 'WILL_CONSIDER' | source: General Creditor sheet", d1.reason)
        self.assertIn("request #%d" % d1.pk, out)
        self.assertIn("Nothing has been applied", out)

    def test_rerun_is_idempotent_and_replaces_only_when_the_proposal_changed(self):
        self._run("--user", "author")
        ids = sorted(CriteriaChangeRequest.objects.values_list("pk", flat=True))
        out = self._run("--user", "author")
        self.assertEqual(sorted(CriteriaChangeRequest.objects.values_list("pk", flat=True)), ids)
        self.assertIn("unchanged", out)

        # the sheet moves on: Bamboo now Accept -> group 1 proposal differs
        group1_title = b.draft_title("creditor_statuses")
        old = CriteriaChangeRequest.objects.get(title=group1_title)
        (self.dir / "General_Creditors.md").write_text(GENERAL.replace("| Bamboo | Will Consider |", "| Bamboo | Accept |"), encoding="utf-8")
        out = self._run("--user", "author")
        old.refresh_from_db()
        self.assertEqual(old.status, CriteriaChangeRequest.STATUS_CANCELLED)
        new = CriteriaChangeRequest.objects.filter(title=old.title, status=CriteriaChangeRequest.STATUS_DRAFT).get()
        self.assertNotEqual(new.pk, old.pk)
        self.assertIn("replaced", out)
        self.assertIn("changed CreditorCriteria #%d status" % self.bamboo.pk, out)
        self.assertEqual(CriteriaChangeRequest.objects.filter(status=CriteriaChangeRequest.STATUS_DRAFT).count(), 5)

    def test_requires_a_user_unless_dry_run(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._run()
        with self.assertRaises(CommandError):
            self._run("--user", "nobody")
