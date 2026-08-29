"""
Tests for attaching CouncilTaxEvidence onto the assess response — the
"show ctax evidence in the assessment report" follow-up. Unit-tests
attach_council_tax_evidence() / _council_name_match() directly (no need to
exercise the full AssessCaseView HTTP path, which would require mocking
the Aryza fetch layer) — this is where all the actual logic lives; the
view just calls it and merges the result into the response, per
AssessCaseView.post.
"""
from django.test import TestCase

from debt_app.models import CouncilTaxEvidence
from debt_app.views.criteria_views import _council_name_match, attach_council_tax_evidence


class CouncilNameMatchTests(TestCase):
    def test_matches_substring_either_direction(self):
        self.assertTrue(_council_name_match("Flintshire", "Flintshire County Council"))
        self.assertTrue(_council_name_match("Flintshire County Council", "Flintshire"))

    def test_case_insensitive(self):
        self.assertTrue(_council_name_match("flintshire", "FLINTSHIRE COUNTY COUNCIL"))

    def test_no_match(self):
        self.assertFalse(_council_name_match("Flintshire", "Dorset County Council"))

    def test_empty_inputs_never_match(self):
        self.assertFalse(_council_name_match("", "Flintshire County Council"))
        self.assertFalse(_council_name_match("Flintshire", ""))
        self.assertFalse(_council_name_match(None, "Flintshire County Council"))

    def test_short_name_guard(self):
        # A 1-2 character name would otherwise substring-match almost anything.
        self.assertFalse(_council_name_match("EE", "Flintshire County Council"))


class AttachCouncilTaxEvidenceTests(TestCase):
    def _make_evidence(self, **overrides):
        defaults = dict(
            aryza_reference="REF-1",
            extraction_status="extracted",
            account_reference="801302683",
            balance_pence=204700,
            council_name="Flintshire",
            liability_order_court="Mold Magistrates Court",
            client_salutation_name="MISS WYLIE",
        )
        defaults.update(overrides)
        return CouncilTaxEvidence.objects.create(**defaults)

    def test_returns_evidence_list_even_with_no_matching_position(self):
        self._make_evidence()
        result = attach_council_tax_evidence([], "REF-1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["council_name"], "Flintshire")
        self.assertEqual(result[0]["balance_pence"], 204700)

    def test_attaches_onto_matching_council_tax_position(self):
        self._make_evidence()
        positions = [
            {"creditor_name": "Flintshire County Council", "debt_type_normalised": "council_tax"},
            {"creditor_name": "Halifax", "debt_type_normalised": "personal_loan"},
        ]
        attach_council_tax_evidence(positions, "REF-1")
        self.assertIn("council_tax_evidence", positions[0])
        self.assertEqual(positions[0]["council_tax_evidence"]["account_reference"], "801302683")
        self.assertNotIn("council_tax_evidence", positions[1])

    def test_non_matching_council_name_does_not_attach(self):
        self._make_evidence(council_name="Dorset")
        positions = [{"creditor_name": "Flintshire County Council", "debt_type_normalised": "council_tax"}]
        attach_council_tax_evidence(positions, "REF-1")
        self.assertNotIn("council_tax_evidence", positions[0])

    def test_extracted_empty_evidence_is_excluded(self):
        self._make_evidence(extraction_status="extracted_empty", council_name="", account_reference="")
        result = attach_council_tax_evidence([], "REF-1")
        self.assertEqual(result, [])

    def test_only_returns_evidence_for_the_requested_reference(self):
        self._make_evidence()
        self._make_evidence(aryza_reference="OTHER-REF", council_name="Dorset")
        result = attach_council_tax_evidence([], "REF-1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["council_name"], "Flintshire")
