"""
Regression tests for client-address extraction from credit reports.

Credit reports never carry a creditor's own postal address — only the
applicant's (Aryza: a single "Current Address:" line near the report header;
Valid8-style Experian search: an "Address:" line repeated against every CAIS
account block). These tests pin down:
  - _clean_address() normalising PDF text-extraction artefacts
  - Aryza's report-level client_address extraction, including the two
    real-report wrap artefacts (orphaned postcode / glued postcode)
  - Valid8's per-account address capture and the report-level client_address
    derived from the first non-empty one
  - the genuine-Experian "Consumer Credit Report" layout (bullet-prefixed
    "Current Address:" field, no per-account address) falling back to the
    same Aryza-style extractor instead of coming back empty

No PDF fixtures (media/ is gitignored) — layouts below are copied verbatim
from real production reports' pdfplumber text output.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    _clean_address,
    _extract_client_address,
    _parse_valid8_account,
    _split_valid8_accounts,
    extract_credit_report,
)


class CleanAddressTests(SimpleTestCase):
    def test_strips_stray_trailing_comma_and_whitespace(self):
        self.assertEqual(
            _clean_address("33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW, "),
            "33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
        )

    def test_collapses_whitespace_runs(self):
        self.assertEqual(
            _clean_address("26  Cosford   Garth,  Bransholme, Hull HU7 4LD"),
            "26 Cosford Garth, Bransholme, Hull HU7 4LD",
        )

    def test_splits_glued_postcode(self):
        self.assertEqual(
            _clean_address("33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT102FW"),
            "33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
        )

    def test_leaves_already_spaced_postcode_untouched(self):
        addr = "26 Cosford Garth, Bransholme, Hull HU7 4LD"
        self.assertEqual(_clean_address(addr), addr)

    def test_collapses_empty_field_between_commas(self):
        # Verified verbatim in a real report: a blank county field leaves a
        # double comma in the source text itself, not a PDF artefact.
        self.assertEqual(
            _clean_address("17, HANMER ROAD, LIVERPOOL, , L32 0RP"),
            "17, HANMER ROAD, LIVERPOOL, L32 0RP",
        )

    def test_empty_input_returns_empty_string(self):
        self.assertEqual(_clean_address(""), "")
        self.assertEqual(_clean_address(None), "")


class AryzaClientAddressTests(SimpleTestCase):
    def test_extracts_current_address_line(self):
        text = "\n".join([
            "Name: Mrs Theresa Topp",
            "Current Address: 26 Cosford Garth, Bransholme, Hull HU7 4LD",
            "Report generated 2026-01-01",
        ])
        self.assertEqual(
            _extract_client_address(text),
            "26 Cosford Garth, Bransholme, Hull HU7 4LD",
        )

    def test_missing_address_returns_empty_string(self):
        self.assertEqual(_extract_client_address("Name: Mrs Theresa Topp"), "")

    def test_wrapped_address_pulls_in_the_orphaned_postcode(self):
        # Verified against a real production report: a long address wraps
        # onto the next PDF text line with no label of its own, taking the
        # entire postcode with it. A naive single-line regex silently
        # truncates the address at "Coventry CV6", dropping "6AH".
        text = "\n".join([
            "Current Address: 42 Rowleys Green Lane, Longford, Coventry CV6",
            "6AH",
            "Previous Addresses: -",
            "Halifax Credit Card CC",
        ])
        self.assertEqual(
            _extract_client_address(text),
            "42 Rowleys Green Lane, Longford, Coventry CV6 6AH",
        )

    def test_wrapped_address_with_glued_postcode_across_two_lines(self):
        # Also verified against a real report: the wrap can land mid-town,
        # and the postcode itself can ALSO be glued (no space) on top of
        # that — both artefacts must be fixed in one pass.
        text = "\n".join([
            "� Current Address: 3, DUNSIL ROAD, MANSFIELD WOODHOUSE, MANSFIELD,",
            "NOTTINGHAMSHIRE, NG197GD",
            "� Voters Roll: Not Confirmed at Address",
        ])
        self.assertEqual(
            _extract_client_address(text),
            "3, DUNSIL ROAD, MANSFIELD WOODHOUSE, MANSFIELD, NOTTINGHAMSHIRE, NG19 7GD",
        )

    def test_continuation_stops_at_the_next_labelled_field(self):
        # A short address that does NOT wrap must not accidentally swallow
        # the next field's line just because it also lacks its own label
        # look-ahead — the ':' on "Previous Addresses:" is what stops it.
        text = "\n".join([
            "Current Address: 44 Saunders Park Rise, Brighton BN2 4EU",
            "Previous Addresses: Ground Floor Flat, 83 Kimberley Road, Brighton BN2",
            "4EN",
        ])
        self.assertEqual(
            _extract_client_address(text),
            "44 Saunders Park Rise, Brighton BN2 4EU",
        )


class Valid8AddressTests(SimpleTestCase):
    def _block(self, name, address, company, status="Active"):
        return "\n".join([
            name,
            f"Address: {address}",
            status,
            "Company Type: Utility",
            "Account Type: Public Utility",
            f"Company: {company}",
            "Start Date: 21-08-2023",
            "Current Balance: £70",
        ])

    def test_split_captures_the_address_anchoring_each_block(self):
        text = "\n".join([
            "MS JANICE DOYLE",
            "Address: 33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
            "Active",
            "Company: BRITISH GAS",
            "MS JANICE DOYLE",
            "Address: 33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
            "Active",
            "Company: LLOYDS BANK CURRENT ACCOUNTS",
        ])
        blocks = _split_valid8_accounts(text)
        self.assertEqual(len(blocks), 2)
        for address, _ in blocks:
            self.assertEqual(
                address, "33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW"
            )

    def test_parsed_account_carries_its_address(self):
        text = self._block(
            "MS JANICE DOYLE",
            "33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
            "BRITISH GAS",
        )
        blocks = _split_valid8_accounts(text)
        self.assertEqual(len(blocks), 1)
        address, block_text = blocks[0]
        parsed = _parse_valid8_account(address, block_text)
        self.assertIsNotNone(parsed)
        self.assertEqual(
            parsed["address"], "33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW"
        )

    def test_missing_address_yields_none_not_empty_string(self):
        # _split_valid8_accounts always supplies *some* address (it's the
        # anchor), but a directly-constructed empty address should still
        # come out as None rather than "" so callers can tell "known blank"
        # apart from "field absent".
        parsed = _parse_valid8_account("", self._block("X", "Y", "BRITISH GAS"))
        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed["address"])


def _fake_pdf_open(full_text):
    """Monkeypatch target for pdfplumber.open() returning fixed page text,
    so extract_credit_report()'s full pipeline can be exercised without a
    real PDF fixture (media/ is gitignored — see module docstring)."""
    page = MagicMock()
    page.extract_text.return_value = full_text
    pdf = MagicMock()
    pdf.pages = [page]
    pdf.__enter__.return_value = pdf
    pdf.__exit__.return_value = False
    return pdf


class GenuineExperianConsumerReportAddressTests(SimpleTestCase):
    """
    A third, genuine-Experian layout — not the classic "{Creditor} -
    {Category}" CAIS format, not the Valid8IP-anchored bureau-search format —
    verified against a real production report. It carries the applicant's
    address as the exact same bullet-prefixed "Current Address:" summary
    field Aryza Advize uses, with no per-account address at all. Before this
    fix, extract_credit_report() only ever tried the Valid8 per-account
    address for an "Experian"-detected report, so this layout silently came
    back with client_address == "".
    """

    def test_falls_back_to_aryza_style_current_address_field(self):
        full_text = "\n".join([
            "Consumer Credit Report",
            "ADAM OSBORNE",
            "Experian Reference ACZT4CWL4Q",
            "Issue Date and Time 04/03/2026 17:26:04",
            "Summary",
            "Search Details",
            "� Applicant: ADAM OSBORNE",
            "� DOB: 12-06-1993",
            "� Current Address: 3, DUNSIL ROAD, MANSFIELD WOODHOUSE, MANSFIELD,",
            "NOTTINGHAMSHIRE, NG197GD",
            "� Voters Roll: Not Confirmed at Address",
        ])
        with patch("pdfplumber.open", return_value=_fake_pdf_open(full_text)):
            result = extract_credit_report("fake.pdf")
        self.assertEqual(result["agency"], "Experian")
        self.assertEqual(
            result["client_address"],
            "3, DUNSIL ROAD, MANSFIELD WOODHOUSE, MANSFIELD, NOTTINGHAMSHIRE, NG19 7GD",
        )

    def test_valid8_address_still_takes_precedence_when_present(self):
        # Guard against the fallback overwriting a real Valid8 per-account
        # address with a spurious/absent Aryza-style match.
        full_text = "\n".join([
            "Consumer Credit Report",
            "Provider: Experian",
            "MS JANICE DOYLE",
            "Address: 33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
            "Active",
            "Company Type: Utility",
            "Account Type: Public Utility",
            "Company: BRITISH GAS",
            "Start Date: 21-08-2023",
            "Current Balance: £70",
        ])
        with patch("pdfplumber.open", return_value=_fake_pdf_open(full_text)):
            result = extract_credit_report("fake.pdf")
        self.assertEqual(result["agency"], "Experian")
        self.assertEqual(
            result["client_address"],
            "33, ROBIN WAY, STURMINSTER NEWTON, DORSET, DT10 2FW",
        )
