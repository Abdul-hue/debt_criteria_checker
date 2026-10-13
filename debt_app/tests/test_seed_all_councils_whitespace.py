"""
seed_all_councils must not create a second row for a council whose database
name differs from the markdown only in whitespace (some rows were created
straight from the workbook with line breaks inside the name).
"""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from debt_app.models import CouncilRule

COUNCILS = """# Councils

| # | Council | Status | Notes | Updated Criteria | Criteria Changed From Rej Date | Contact Name | Contact Number |
|---|---------|--------|-------|------------------|-------------------------------|--------------|----------------|
| 1 | Liney Borough Council was abolished.   Now Elsewhere Council | Reject | now rejects |  |  |  |  |
| 2 | Brand New Town Council | Accept | new |  |  |  |  |
"""


class SeedAllCouncilsWhitespaceTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "Excel Criteria").mkdir()
        (self.root / "Excel Criteria" / "Councils.md").write_text(COUNCILS, encoding="utf-8")
        CouncilRule.objects.filter(council_name__icontains="Brand New Town").delete()
        self.liney = CouncilRule.objects.create(
            council_name="Liney Borough Council was abolished.\n\n\nNow Elsewhere Council", status="DO_NOT_VOTE",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_existing_row_matched_ignoring_whitespace(self):
        before = CouncilRule.objects.count()
        out = io.StringIO()
        # The county-routing pin step that follows seeding is strict about the
        # full council list; it is not what this test is about.
        with override_settings(BASE_DIR=self.root), \
                patch("debt_app.county_routing_seed.seed_county_routing"), \
                patch("debt_app.county_routing_seed.apply_alias_pins"):
            call_command("seed_all_councils", stdout=out)
        self.assertEqual(CouncilRule.objects.count(), before + 1)        # only Brand New Town
        self.assertEqual(CouncilRule.objects.filter(council_name__icontains="Liney").count(), 1)
        self.assertEqual(CouncilRule.objects.get(pk=self.liney.pk).status, "DO_NOT_VOTE")  # not overwritten without --overwrite
        self.assertIn("CREATED: Brand New Town Council", out.getvalue())
        self.assertNotIn("CREATED: Liney", out.getvalue())
