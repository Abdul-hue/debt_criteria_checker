"""
Sync CreditorCriteria from the Excel Criteria markdown files.

Sources: Which_Representative_Criteria.md, General_Creditors.md, Dividends_Criteria.md
(generated from the workbook by `manage.py export_excel_criteria`).

    python manage.py seed_creditor_criteria [--dry-run]            # notes-only (default, safe)
    python manage.py seed_creditor_criteria --include-manual        # also touch admin-edited rows' notes
    python manage.py seed_creditor_criteria --full [--dry-run]      # legacy: overwrite every parsed field

Default mode is NOTES-ONLY: it updates free text and contact details on matched
creditors, creates creditors that do not exist yet, and applies the agreed
renames (RENAMED_ROWS). It never writes status, representative, dividend
minimums, reject flags or trading names on an existing row: those are managed
fields and change only through the criteria change workflow
(build_criteria_change_from_excel -> trial -> second-manager approval).

This command never deletes rows. Rows that are in the database but not in the
markdown are listed as orphans for a human to look at. (The earlier "strict
sync" deleted them, which is how hand-restored creditors went missing in
August 2026.)
"""

import os
import re
from django.conf import settings
from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria
from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name
from debt_app.services.excel_criteria import RENAMED_ROWS

# ---------------------------------------------------------------------------
# Structured conditional criteria (manual translation of the free-text
# "Notes/Criteria" column in Excel Criteria/General_Creditors.md into the
# structured fields the engine actually evaluates).
#
# WHY THIS LIVES HERE (not in a migration): the seed command is the "truth
# import". Keeping these here means every reseed re-applies them and they are
# never clobbered. Applied case-insensitively after the main upsert. Only fields
# the engine CONSUMES are listed; each carries its source quote. Keyed by the
# canonical DB creditor_name (verified to resolve via iexact).
#
# Engine-consumption verified 2026-06-21. Excluded on purpose:
#   - account_age_months on already-blanket-REJECT creditors (redundant)
#   - reject_if_second_iva (engine can't tell "failed" from "any prior IVA")
#   - reject_if_never_made_payment / requires_grant_overpayment_only
#     (reject-everyone trap until the payload signal is confirmed)
# ---------------------------------------------------------------------------

STRUCTURED_CRITERIA = {
    # --- min loan age (account_age_months): credit-report Start Date < N → reject ---
    "Acorn Banking": {"account_age_months": 6},                       # "reject if less than 6 months old"
    "Admiral Loans": {"account_age_months": 6,                        # "running cases: 6 months or older" (was 3; workbook 24.08.26)
                      "reject_if_second_iva": True,                   # "REJECT IF PREVIOUS IVA CONFIRMED THIS 24.08.26"
                      "reject_if_ccj": True, "reject_if_aoe": True},  # "no CCJ, no AOE"
    "CAMBRIAN credit union": {"account_age_months": 6,                # "REJECT IF LOAN LESS THAN 6 MONTHS OLD"
                              "reject_if_in_dmp": True},              # "CLIENT IS ALREADY IN A DMP"
    "Clockwise Credit Union": {"account_age_months": 2,                # "loan taken out in last 8 weeks" (8wk≈2mo)
                              "min_dividend_pence": 50},              # "MUST BE 50p£" — not in Dividends_Criteria.md
    "Everyday Loans": {"account_age_months": 6,                      # "Loan must be 6 months old"
                       "open_banking_access": True,                  # "open banking required"
                       "reject_if_debt_repayable_within_months": 120},  # "cannot be debt repayment in 10 years"
    "Fair for you Enterprise": {"account_age_months": 1,            # "NO LESS THAN 30 DAYS OLD"
                                "reject_if_recent_spend_months": 1},  # "reject if spent within last month"
    "Fintern limited / Abound - NOT WPM": {"account_age_months": 6,  # "reject if under 6 months"
                                          "open_banking_access": True},  # "open banking required"
    "Hitachi Capital/Credit / Novuna": {"account_age_months": 1},    # "reject if taken out in less than 1 month"
    "Ikano Finance": {"account_age_months": 12,                      # "if under a year old"
                      "reject_if_never_made_payment": True},         # "reject if no payment has been made"
    "Loans at home": {"account_age_months": 1,                       # "if loan taken out in last 1 months"
                      "reject_if_never_made_payment": True},         # "reject if no payment has been made"
    "Manchester Credit Union": {"account_age_months": 3},            # manager 2026-10-21: "REJECT IF THE LOAN WAS TAKEN IN THE LAST 3 MONTHS"
    "Loans by Mal": {"account_age_months": 3,                       # "REJECT IF LESS THAN 3 MONTHS"
                     "reject_if_debt_repayable_within_months": 84,   # "REPAID IN 84 MONTHS"
                     "reject_if_ie_doesnt_match_application": True,  # "APPLICATION DOES NOT MATCH OUR I&E"
                     "young_account_months": 6,                      # "if under 6 months but older than 3 months - has to 40p/£"
                     "young_account_min_dividend_pence": 40},        #   (workbook 2026-10-12)
    "Loans 2 Go": {"account_age_months": 1,                          # "if loan less than 1 month old"
                   "reject_if_never_made_payment": True,             # "reject if no payment has been made"
                   "fraud_claim_risk": True},                        # "reject and claim fraud"
    "Mutual Clothing": {"account_age_months": 6},                    # "IF TAKEN OUT RECENTLY WILL REJECT (6 MONTHS)"
    "One Stop Money Shop": {"account_age_months": 3},                # "LESS THAN 3 MONTHS OLD"
    "Ratesetter": {"min_dividend_pence": 25,                          # Dividends: "25p"
                   "young_account_months": 6,                        # "if under 6 months old it 50p" (confirmed 2026-10-13)
                   "young_account_min_dividend_pence": 50},
    "Savvy (TICK TOCK LOANS)": {"account_age_months": 6,             # "IF LOAN IS LESS THAN 6 MONTHS OLD"
                                "fraud_claim_risk": True},           # "CALL OUT FRAUD"
    "Transave UK Credit Union": {"account_age_months": 3,            # "needs to be at least 3 months old"
                                 "min_dividend_pence": 60},          # "NEEDS TO BE 60P/£" — Dividends name "Transave Credit Union" differs, so must set here
    "UK Credit Ltd": {"account_age_months": 6},                      # "WILL REJECT IF LOAN IS UNDER 6 MONTHS"
    "Wiltshire and Swindon Credit Union": {"account_age_months": 6}, # "reject if less than 6 months old"
    "Bamboo": {"account_age_months": 3,                              # "REJECT IF LESS THAN 3 MONTHS"
               "reject_if_never_made_payment": True,                # "reject if no payment has been made"
               "reject_if_debt_repayable_within_months": 96},       # "repaid in 96 months"
    "TM Advances": {"account_age_months": 6,                        # "reject if under 6 months"
                    "reject_if_ie_doesnt_match_application": True,  # "I&E has to match loan application"
                    "open_banking_access": True},                    # "open banking required"

    # --- debt repayable within N months (balance/DI < N → reject) ---
    "Amigo": {"reject_if_debt_repayable_within_months": 84},             # "repaid in 84 months"
    "Lifestyle Loans": {"reject_if_debt_repayable_within_months": 80},   # "repaid in 80 months"
    "Hastings Direct Loans": {"reject_if_debt_repayable_within_months": 120},  # "repayed in 10 years"

    # --- equity > debt (homeowner, 85% LTV) → reject ---
    "American Express Service": {"reject_if_equity_exceeds_debt": True},   # "REJECT IF MORE EQUITY THAN THEIR DEBT"
    # "HM Revenue & Customs": the sheet's "WILL REJECT if more equity than their
    # debt (100% HOUSE VALUATION)" is TIG-15.4 (equity at 100% vs the HMRC
    # balance). The per-creditor reject_if_equity_exceeds_debt flag (85% vs
    # total unsecured debt) was a stand-in and is being switched off through
    # the change workflow (2026-10-13); it must not be re-applied by a reseed.
    "Shawbrook": {"reject_if_equity_exceeds_debt": True},                  # "MORE EQUTIY THEN THERE DEBT WILL REJECT"
    "The Funding Corporation": {"reject_if_equity_exceeds_debt": True,     # "reject if more equity than their debt"
                                "min_dividend_pence": 50},                 # "Vote to accept with 50p dividend" — Dividends "Funding Corp" differs
    "Funding Corporation": {"min_dividend_pence": 50},                     # "If div is lower than 50p/£ for a 5 year IVA they will reject"
    "Funding Circle": {"reject_if_equity_exceeds_debt": True,             # "WILL REJECT IF EQUITY IN PROPERTY"
                     "min_dividend_pence": 30},                            # "30p/£ minimum"
    "IWOCA / IWOKA LOANS": {"reject_if_equity_exceeds_debt": True,         # "cannot be more equity than their debt"
                            "requires_pg_called_up": True,                 # "PG must have been called up"
                            "min_dividend_pence": 50},                     # "50P/£ MINIMUM" — not in Dividends file

    # --- majority share % → reject ---
    "Commsave Credit Union": {"reject_if_majority_share_exceeds_pct": 50,  # "Reject if they own over 50%"
                              "reject_if_in_dmp": True,                    # "REJECT IF CLIENT IS IN DMP"
                              "min_dividend_pence": 50},                   # "looks like will accept around 50p"
    "Plata Loans (BAMBOO)": {"reject_if_majority_share_exceeds_pct": 85},  # "more then 85% then they will reject"

    # --- financed asset must be returned → reject (dormant unless payload signal) ---
    "Advantage Finance": {"reject_if_client_still_has_asset": True,        # "Car needs to have gone back"
                          "reject_if_ccj": True, "reject_if_aoe": True},   # "REJECT IF ... AOE OR CCJ"
    "First Response Finance": {"reject_if_client_still_has_asset": True},  # "car needs to have gone back"
    "Marsh Finance": {"reject_if_client_still_has_asset": True,            # "car had to have gone back"
                      "min_dividend_pence": 70},                           # "confirmed want 70p/£" — not in Dividends file
    "Oodle Finance": {"reject_if_client_still_has_asset": True},           # "MUST HAVE THE VEHICLE IN THEIR POSSESSION"
    "Billings finance": {"reject_if_client_still_has_asset": True},        # "car needs to have gone back"
    "Santander Consumer Finance": {"reject_if_client_still_has_asset": True},  # "car needs to have gone back"
    "Snap on Tools": {"reject_if_client_still_has_asset": True},           # "REJECT IF CUSTOMER STILL HAS TOOLS"
    "Moneybarn": {"reject_if_client_still_has_asset": True,                # "CAR MUST HAVE BEEN RETURNED ... OTHERWISE REJECT"
                  "fees_cap_percentage": 25,                               # "fees capped at 25% of TR"
                  "vehicle_arrears_repossession_months": 2,                # "WILL REPOSSESS IF VEHICLE HP HAS 2 MONTHS OR MORE ARREARS"
                  "requires_arrangement_call_before_proposing": True},     # "if arrears MUST HAVE CALL TO CONFIRM ARRANGEMENT IN PLACE BEFORE PROPSING"

    # --- minimum dividend (pence per pound) ---
    # Only creditors where Dividends_Criteria.md uses a DIFFERENT name than General_Creditors.md
    # (exact-name matches are already handled by the Dividends parsing step in _parse_strict_sources).
    # Creditors only in General notes (not in Dividends file) are also listed here.
    "Asset Link Capital": {"min_dividend_pence": 50},          # Dividends: "Asset Link: 50p" — name differs from "Asset Link Capital"
    "CARDIFF CREDIT UNION(I)": {"min_dividend_pence": 45},     # Dividends: "Cardiff Credit Union: 45p" — name differs from "CARDIFF CREDIT UNION(I)"
    "Cardiff & Vale Credit Union, Cardiff and Vale": {"min_dividend_pence": 50},  # "will only consider 50p/£" — not in Dividends
    "Castle Community Bank": {"min_dividend_pence": 30},       # "the case has to be proposed at 30p/£" — not in Dividends
    "FCE Bank PLC": {"min_dividend_pence": 75},                # Dividends: "FCE Bank: 75p" — name differs from "FCE Bank PLC"
    "GLENSIDE FINANCE LTD": {"min_dividend_pence": 25},        # Dividends: "Glenside Finance: 25p" — name differs from "GLENSIDE FINANCE LTD"
    "HULL & EAST YORKSHIRE CREDIT UNION (I) Hey CU (Hey Credit Union)": {"min_dividend_pence": 60},  # Dividends: "Hull and East Yorkshire CU: 60p"
    "Match the Cash t/a Guarantor My Loan (Match the Cash trading name)": {
        "min_dividend_pence": 100,                             # Dividends: "Guarantor My Loan: 100P/£" (was 50p; workbook 2026-10-12) — name differs
        "reject_if_ie_doesnt_match_application": True,         # "I&E has to match loan application"
    },
    "NHS CREDIT UNION (I)": {"min_dividend_pence": 78},        # "WANT 78P/£" — not in Dividends
    "Norwich Trust Limited": {"min_dividend_pence": 100},      # "WILL ONLY ACCEPT 100P/£" — not in Dividends
    "Perch Capital Limited": {"min_dividend_pence": 5},        # "Require a minimum dividend of 5p/£" — not in Dividends
    "Specialist Motor Finance": {"min_dividend_pence": 50},    # Dividends: "Specialist Motor Finance: 50p" — exact name match but safe to set here too
    "Travis Perkins": {"min_dividend_pence": 50},              # "WILL ONLY CONSIDER ANYTHING ABOVE 50P/£" — not in Dividends
    "Buddy Loans t/a Advancis Ltd": {"min_dividend_pence": 50},  # "minimum of 50P/£ DIV" — not in Dividends
    "DRAGON SAVERS CREDIT UNION": {"min_dividend_pence": 68},    # "68p/£ minimum" — not in Dividends file
    "Partners Credit Union": {"min_dividend_pence": 65},         # "65p/£ minimum" — not in Dividends file
    "Believe Housing": {"min_dividend_pence": 40},               # "minimum 40p/£" — not in Dividends_Criteria.md
    "Beyond Housing": {"min_dividend_pence": 30},                # "30p/£ minimum" — not in Dividends_Criteria.md
    "South East Water": {"min_dividend_pence": 40},              # "40p/£ confirmed 4/7/25" — not in Dividends_Criteria.md

    # --- flags ---
    "South Yorkshire Credit Union": {"fraud_claim_risk": True},           # "reject if taken out fraudulently"
    "Unify Credit Union Limited": {"account_age_months": 6,               # "reject if under 6 months"
                                  "reject_if_ie_doesnt_match_application": True,  # "I&E has to match loan application"
                                  "fraud_claim_risk": True},             # "THEY ALSO CLAIM FRAUD"
    "No1 Copperpot Credit Union": {"reject_if_police_employed": True},    # "CANNOT INCLUDE IF STILL EMLOYED BY THE POLICE"
    "Student Loans Company": {"requires_grant_overpayment_only": True},   # "grant overpayment only"
    "Volkswagen Financial Services": {"termination_risk_if_vehicle_on_finance": True},  # "will terminate ... if car is on finance"

    # --- recent spend rejection (gold_transactions name-match within N months → reject) ---
    "Enterprise Credit Union":    {"reject_if_recent_spend_months": 3},
    "Manchester Credit Union":    {"reject_if_recent_spend_months": 3},
    "Great Western Credit Union": {"reject_if_recent_spend_months": 3},
    "Studio Cards & Gifts":       {"reject_if_recent_spend_months": 3},
}


# ---------------------------------------------------------------------------
# Trading name overrides (engine-consumed field not representable in the MD
# sources — Which_Representative_Criteria.md / General_Creditors.md are flat
# name lists with no trading-names column).
#
# WHY THIS LIVES HERE (not a migration, not a direct DB/admin edit): the main
# upsert above unconditionally sets `trading_names` from the parsed MD data,
# which is always `[]` — there is nowhere else for it to come from. A value
# added any other way (a one-off migration, a manual admin edit) is silently
# wiped back to `[]` on the very next reseed. This is exactly what happened to
# Northridge Finance's trading_names on Santander Consumer Finance, seeded
# once by migration 0031 and gone by the next `seed_creditor_criteria` run.
# Keeping trading names here means every reseed re-applies them — never
# clobbered, same principle as STRUCTURED_CRITERIA above.
#
# Case-insensitive name match; entries are MERGED into whatever the row
# already has (not replaced), so this only ever adds names, never removes one
# added by a future MD update.
TRADING_NAMES_OVERRIDES = {
    "JD Williams": ["J D Williams", "JD Williams & Company", "Simply Be",
                    "Jacamo", "Fashion World", "Marisota"],
    "Anderson Brookes": ["Anderson Brookes Solicitors"],
    "Credit4": ["Credit 4"],
    "CCC Debt Management": ["CCC", "Complete Credit Control"],
    "The Money Platform": ["Money Platform"],
    "Cashplus": ["Cashplus Bank", "Advanced Payment Solutions Ltd", "Zempler Bank Limited"],
    "Santander Consumer Finance": ["Northridge Finance", "Northridge Finance Ltd"],
    "Zilch": ["Zilch Technology Limited", "Zilch Technology LTD"],   # appears on real cases as all three forms
}


# ---------------------------------------------------------------------------
# Banking group mappings (manual enrichment not in the MD file)
# ---------------------------------------------------------------------------

PARENT_GROUPS = {
    "RBS Group": [
        "The Royal Bank of Scotland Plc", "NatWest Bank", "Ulster Bank",
        "Coutts", "Think Banking", "Lombard", "Mint",
    ],
    "Lloyds Group": [
        "Lloyds Bank", "Bank of Scotland", "Halifax", "Blackhorse",
        "Birmingham Midshires", "MBNA", "Virgin Money",
        "Cheltenham and Gloucester", "Intelligent Finance", "AA", "Saga",
    ],
    "Barclays Group": [
        "Barclays Bank", "Barclaycard", "Woolwich", "Standard Life Bank",
    ],
    "HSBC Group": [
        "HSBC", "First Direct", "Marks and Spencer Financial Services",
    ],
    "Santander Group": [
        "Santander", "Cahoot", "Alliance and Leicester", "Abbey National",
    ],
    "Nationwide Group": [
        "Nationwide",
    ],
    "Shop Direct Group": [
        "Shop Direct", "Very", "Littlewoods", "JD Williams",
    ],
    "Virgin Money Group": [
        "Clydesdale Bank", "Yorkshire Bank",
    ],
    "Everyday Loans Group": [
        "George Banco", "Trust Two",
    ],
    "Co-op Group": [
        "Co-operative Bank", "Smile", "Britannia Building Society",
    ],
    "BoI Group": [
        "Bank of Ireland", "Post Office",
    ],
    "Yorkshire Group": [
        "Yorkshire BS", "Barnsley BS", "Chelsea BS", "Norwich and Peterborough BS",
    ],
    "Skipton Group": [
        "Skipton BS", "Chesham BS", "Scarborough BS",
    ],
    "Coventry Group": [
        "Coventry BS", "Stroud and Swindon BS",
    ],
}


def _parse_pence(s):
    """Extracts integer pence from string like '50p' or '50'."""
    if not s:
        return None
    match = re.search(r"(\d+)", s)
    if match:
        return int(match.group(1))
    return None


def _parse_status(s):
    """Maps General_Creditors.md 'Accept / Reject' column to CreditorCriteria.STATUS_CHOICES."""
    if not s:
        return None
    s_lower = s.lower().strip()
    if any(kw in s_lower for kw in ["do not vote", "pod only", "no voting", "non voter", "not sure how they vote", "unaware how they vote"]):
        return "DO_NOT_VOTE"
    elif "will consider" in s_lower:
        return "WILL_CONSIDER"
    elif "unknown" in s_lower:
        return "UNKNOWN"          # stance not yet confirmed by the sheet owner (never an acceptance)
    elif "reject" in s_lower:
        return "REJECT"
    elif "accept" in s_lower:
        return "ACCEPT"
    elif "conditional" in s_lower:
        return "CONDITIONAL_VOTER"
    return None


def _resolve_creditor_name(raw_name: str) -> str:
    """Resolve a raw creditor name to its canonical form using CREDITOR_ALIAS_MAP."""
    if not raw_name:
        return raw_name
    normalised = normalise_creditor_name(raw_name)
    return CREDITOR_ALIAS_MAP.get(normalised, raw_name.strip())


def _parse_strict_sources():
    """Parses Which_Representative_Criteria.md, General_Creditors.md, and Dividends_Criteria.md."""
    criteria_dir = os.path.join(settings.BASE_DIR, "Excel Criteria")
    if not os.path.exists(criteria_dir):
        criteria_dir = os.path.join(os.path.dirname(settings.BASE_DIR), "Excel Criteria")

    valid_creditors = {} # name -> {rep, source, group, trading_names, min_dividend_pence, dividend_notes}
    
    # 1. Parse Which_Representative_Criteria.md (Source: REPRESENTATIVE)
    rep_md = os.path.join(criteria_dir, "Which_Representative_Criteria.md")
    if os.path.exists(rep_md):
        current_rep = "NONE"
        rep_map = {
            "TIX": "TIX",
            "WATCH": "WATCH",
            "WPM": "WATCH",
            "EVOLVE": "EVOLVE",
            "EVERYDAY LOANS": "EVERYDAY_LOANS"
        }
        with open(rep_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("## "):
                    section = line[3:].strip().upper()
                    found = False
                    for key, val in rep_map.items():
                        if key in section:
                            current_rep = val
                            found = True
                            break
                    if not found: current_rep = "NONE"
                    continue
                if line.startswith("- "):
                    name = line[2:].strip()
                    if name:
                        valid_creditors[name] = {
                            "representative": current_rep,
                            "source": "REPRESENTATIVE",
                            "trading_names": [],
                            "parent_group": None,
                            "min_dividend_pence": None,
                            "dividend_notes": None
                        }

    # 2. Parse General_Creditors.md (Source: GENERAL_CREDITOR)
    gen_md = os.path.join(criteria_dir, "General_Creditors.md")
    if os.path.exists(gen_md):
        with open(gen_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("|"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) > 1:
                        name = parts[1]
                        if name and name not in ["Creditor", "Group Name", "Entity", "#", "Council"] and not re.match(r"^[- :|]+$", name):
                            # Extract fields
                            status = parts[2] if len(parts) > 2 else None
                            notes = parts[3] if len(parts) > 3 else None
                            updated_criteria = parts[4] if len(parts) > 4 else None
                            phone = parts[5] if len(parts) > 5 else None
                            email = parts[6] if len(parts) > 6 else None
                            contact = parts[7] if len(parts) > 7 else None
                            
                            parsed_status = _parse_status(status)
                            
                            if name in valid_creditors:
                                valid_creditors[name]["source"] = "GENERAL_CREDITOR"
                                if parsed_status:
                                    valid_creditors[name]["status"] = parsed_status
                                if notes:
                                    valid_creditors[name]["criteria_notes"] = notes
                                if phone:
                                    valid_creditors[name]["contact_phone"] = phone
                                if email:
                                    valid_creditors[name]["contact_email"] = email
                                if contact:
                                    valid_creditors[name]["contact_name"] = contact
                                if updated_criteria:
                                    valid_creditors[name]["raw_updated_criteria"] = updated_criteria
                            else:
                                valid_creditors[name] = {
                                    "representative": "NONE",
                                    "source": "GENERAL_CREDITOR",
                                    "trading_names": [],
                                    "parent_group": None,
                                    "min_dividend_pence": None,
                                    "dividend_notes": None,
                                    "status": parsed_status,
                                    "criteria_notes": notes,
                                    "contact_phone": phone,
                                    "contact_email": email,
                                    "contact_name": contact,
                                    "raw_updated_criteria": updated_criteria
                                }

    # 3. Parse Dividends_Criteria.md
    div_md = os.path.join(criteria_dir, "Dividends_Criteria.md")
    if os.path.exists(div_md):
        with open(div_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("|"):
                    parts = [p.strip() for p in line.split("|")]
                    # Format: | Creditor | Div Required | Notes |
                    if len(parts) >= 4:
                        name = parts[1]
                        div_req = parts[2]
                        notes = parts[3]
                        if name and name not in ["Creditor", "Div Required"] and not re.match(r"^[- :|]+$", name):
                            pence = _parse_pence(div_req)
                            if name in valid_creditors:
                                valid_creditors[name]["min_dividend_pence"] = pence
                                valid_creditors[name]["dividend_notes"] = notes
                            else:
                                valid_creditors[name] = {
                                    "representative": "NONE",
                                    "source": "DIVIDEND",
                                    "trading_names": [],
                                    "parent_group": None,
                                    "min_dividend_pence": pence,
                                    "dividend_notes": notes
                                }

    # 4. Apply parent groups
    for group_name, members in PARENT_GROUPS.items():
        for member in members:
            for name, data in valid_creditors.items():
                if member.lower() in name.lower() or name.lower() in member.lower():
                    data["parent_group"] = group_name

    return valid_creditors


# ---------------------------------------------------------------------------
# Fields the default (notes-only) mode may write on an existing row.
# Everything the engine decides on — status, representative, dividend
# minimums, reject flags, trading names — is a managed field and changes only
# through the criteria change workflow (see MANAGED_FIELDS in
# debt_app/services/criteria_versioning.py).
# ---------------------------------------------------------------------------
NOTES_ONLY_FIELDS = (
    "criteria_notes", "raw_updated_criteria",
    "contact_name", "contact_email", "contact_phone", "dividend_notes",
)


def _find_row(name):
    row = CreditorCriteria.objects.filter(creditor_name=name).first()
    if row is None:
        row = CreditorCriteria.objects.filter(creditor_name__iexact=name).order_by("pk").first()
    return row


def _new_row_defaults(data):
    """Every parsed field, for a creditor that does not exist yet. A new row has
    no manager-controlled values to protect, so the sheet's stance is its
    starting point (exactly as every existing row was first created)."""
    defaults = {
        "representative": data["representative"],
        "source_sheet": data["source"],
        "is_active": True,
        "trading_names": data["trading_names"],
        "min_dividend_pence": data["min_dividend_pence"],
        "dividend_notes": data["dividend_notes"],
    }
    if data.get("parent_group"):
        defaults["parent_group"] = data["parent_group"]
    for key in ("status", "criteria_notes", "contact_phone", "contact_email",
                "contact_name", "raw_updated_criteria"):
        if data.get(key):
            defaults[key] = data[key]
    return defaults


def _with_trading_name_overrides(name, defaults):
    """New rows only: merge the hand-maintained trading names so a creditor
    created by the sync is matchable from day one. Existing rows keep their
    trading_names (a managed field) untouched in notes-only mode."""
    for crit_name, names in TRADING_NAMES_OVERRIDES.items():
        if crit_name.lower() == name.lower():
            current = list(defaults.get("trading_names") or [])
            defaults["trading_names"] = current + [n for n in names if n not in current]
    return defaults


class Command(BaseCommand):
    help = (
        "Sync CreditorCriteria from the Excel Criteria markdown. Default mode is notes-only: "
        "updates free text and contact details, creates new creditors, applies agreed renames, "
        "and never touches status, representative, dividends, reject flags or trading names. "
        "Never deletes rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would change without writing to the database.",
        )
        parser.add_argument(
            "--full", action="store_true",
            help="Legacy full sync: overwrite every parsed field on existing rows (status, representative, "
                 "dividends, notes) and apply the structured criteria and trading-name overrides. This "
                 "bypasses the criteria change workflow; prefer build_criteria_change_from_excel. "
                 "Never deletes rows.",
        )
        parser.add_argument(
            "--include-manual", action="store_true",
            help="Also update rows last edited by hand in admin (updated_by set). "
                 "Those rows are skipped by default in both modes.",
        )

    # ------------------------------------------------------------------ main
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        full = options["full"]
        include_manual = options["include_manual"]

        try:
            valid_map = _parse_strict_sources()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error parsing sources: {e}"))
            return

        mode = "FULL (legacy, overwrites managed fields)" if full else "NOTES-ONLY"
        self.stdout.write(f"Mode: {mode}{' — DRY RUN, nothing written' if dry_run else ''}")
        if full:
            self.stdout.write(self.style.WARNING(
                "--full overwrites status / representative / dividends on existing rows outside the "
                "criteria change workflow. Use build_criteria_change_from_excel for those instead."
            ))

        # 1. Agreed renames: same primary key, so foreign keys, votes, visibility
        #    rows and audit history all follow the row.
        renamed, self._pending_renames = self._apply_renames(dry_run)

        # 2. Orphans are reported, never deleted.
        pending_pks = {row.pk for row in self._pending_renames.values()}
        orphans = sorted(
            c.creditor_name for c in CreditorCriteria.objects.all()
            if c.creditor_name not in valid_map and c.pk not in pending_pks
        )
        if orphans:
            self.stdout.write(self.style.WARNING(
                f"{len(orphans)} creditor row(s) are in the database but not in the markdown. "
                "They are NOT deleted; retire them through the admin if they are genuinely gone:"
            ))
            for name in orphans[:40]:
                self.stdout.write(f"  [ORPHAN] {name}")
            if len(orphans) > 40:
                self.stdout.write(f"  ... and {len(orphans) - 40} more")

        # 3. Sync
        if full:
            counts = self._full_sync(valid_map, dry_run, include_manual)
        else:
            counts = self._notes_only_sync(valid_map, dry_run, include_manual)
        counts["renamed"] = renamed

        self.stdout.write(self.style.SUCCESS(
            ("Would do" if dry_run else "Done") + ": " + ", ".join(f"{k} {v}" for k, v in counts.items())
        ))

    # --------------------------------------------------------------- renames
    def _apply_renames(self, dry_run):
        """Returns (count, {new_name.lower(): row}); the dict lets a dry run
        treat a not-yet-renamed row as already renamed, so it reports the same
        creates/updates a real run would."""
        renamed = 0
        pending = {}
        for old_name, new_name in RENAMED_ROWS.items():
            row = _find_row(old_name)
            if row is None:
                continue
            if row.creditor_name.lower() == new_name.lower():
                continue
            clash = CreditorCriteria.objects.filter(creditor_name__iexact=new_name).exclude(pk=row.pk).first()
            if clash is not None:
                self.stdout.write(self.style.ERROR(
                    f"  [RENAME SKIPPED] {row.creditor_name!r} -> {new_name!r}: a separate row #{clash.pk} "
                    f"already has the new name. Merge them by hand."
                ))
                continue
            self.stdout.write(f"  [RENAME] #{row.pk} {row.creditor_name!r} -> {new_name!r}")
            if dry_run:
                pending[new_name.lower()] = row
            else:
                row.creditor_name = new_name
                row.save(update_fields=["creditor_name"])
            renamed += 1
        return renamed, pending

    def _row_for(self, name):
        row = _find_row(name)
        if row is None:
            row = getattr(self, "_pending_renames", {}).get(name.lower())
        return row

    # ------------------------------------------------------------ notes-only
    def _notes_only_sync(self, valid_map, dry_run, include_manual):
        created = updated = unchanged = skipped_manual = 0
        for name, data in sorted(valid_map.items()):
            row = self._row_for(name)
            if row is None:
                defaults = _with_trading_name_overrides(name, _new_row_defaults(data))
                self.stdout.write(
                    f"  [CREATE] {name!r} (status {defaults.get('status', 'default')}, "
                    f"representative {defaults['representative']})"
                )
                if not dry_run:
                    CreditorCriteria.objects.create(creditor_name=name, **defaults)
                created += 1
                continue

            if row.updated_by_id and not include_manual:
                self.stdout.write(
                    f"  [SKIP manual] {row.creditor_name!r} was edited by hand in admin "
                    f"(by {row.updated_by}) — notes left as they are (use --include-manual to update)"
                )
                skipped_manual += 1
                continue

            patch = {}
            for field in NOTES_ONLY_FIELDS:
                new_value = data.get(field)
                if new_value and (getattr(row, field) or "") != new_value:
                    patch[field] = new_value
            if patch:
                self.stdout.write(f"  [UPDATE] {row.creditor_name!r}: {', '.join(sorted(patch))}")
                if not dry_run:
                    # queryset.update(): no save() signals, no auto_now bump, no updated_by.
                    CreditorCriteria.objects.filter(pk=row.pk).update(**patch)
                updated += 1
            else:
                unchanged += 1

        self.stdout.write(
            "Managed fields (status, representative, dividends, reject flags, trading names) were not "
            "touched on existing rows. Propose those with build_criteria_change_from_excel."
        )
        return {"created": created, "updated": updated, "unchanged": unchanged, "skipped_manual": skipped_manual}

    # ------------------------------------------------------------------ full
    def _full_sync(self, valid_map, dry_run, include_manual):
        """Legacy behaviour minus deletion: upsert every parsed field, then the
        structured criteria and trading-name overrides."""
        created_count = updated_count = skipped_manual = 0

        for name, data in sorted(valid_map.items()):
            defaults = _new_row_defaults(data)
            existing = self._row_for(name)
            if existing is not None and existing.updated_by_id and not include_manual:
                self.stdout.write(
                    f"  [SKIP manual] {existing.creditor_name!r} was edited by hand in admin "
                    f"(by {existing.updated_by}) — left as it is (use --include-manual to overwrite)"
                )
                skipped_manual += 1
                continue
            if dry_run:
                self.stdout.write(f"  [{'UPDATE' if existing else 'CREATE'}] {name!r}")
                if existing:
                    updated_count += 1
                else:
                    created_count += 1
                continue
            if existing is not None:
                for k, v in defaults.items():
                    setattr(existing, k, v)
                existing.save()
                updated_count += 1
            else:
                CreditorCriteria.objects.create(creditor_name=name, **defaults)
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Full sync complete. Created: {created_count}  Updated: {updated_count}  Skipped (manual): {skipped_manual}"
        ))
        if dry_run:
            return {"created": created_count, "updated": updated_count, "skipped_manual": skipped_manual}

        # Structured conditional criteria (engine-consumed fields). Only sets
        # fields that are still at their unset default (None / False); a value
        # edited in admin or through the change workflow is preserved.
        applied = skipped = 0
        for crit_name, fields in STRUCTURED_CRITERIA.items():
            objs = list(CreditorCriteria.objects.filter(creditor_name__iexact=crit_name))
            if not objs:
                self.stdout.write(self.style.WARNING(
                    f"  [STRUCTURED] no creditor matched '{crit_name}' — criteria not applied"
                ))
                continue
            for obj in objs:
                patch = {}
                for field, value in fields.items():
                    current = getattr(obj, field)
                    if current is None or current is False:
                        patch[field] = value
                    else:
                        skipped += 1
                        self.stdout.write(
                            f"  [STRUCTURED] {obj.creditor_name}.{field} = {current!r} "
                            f"(already set, seed value {value!r} skipped)"
                        )
                if patch:
                    CreditorCriteria.objects.filter(pk=obj.pk).update(**patch)
                    applied += 1
        self.stdout.write(self.style.SUCCESS(
            f"Structured criteria applied to {applied} creditor row(s) "
            f"across {len(STRUCTURED_CRITERIA)} mappings ({skipped} field(s) already set)."
        ))

        # Trading name overrides — merged, never replaced.
        tn_applied = 0
        for crit_name, names in TRADING_NAMES_OVERRIDES.items():
            objs = list(CreditorCriteria.objects.filter(creditor_name__iexact=crit_name))
            if not objs:
                self.stdout.write(self.style.WARNING(
                    f"  [TRADING_NAMES] no creditor matched '{crit_name}' — names not applied"
                ))
                continue
            for obj in objs:
                current = obj.trading_names or []
                merged = current + [n for n in names if n not in current]
                if merged != current:
                    obj.trading_names = merged
                    obj.save(update_fields=["trading_names"])
                    tn_applied += 1
        self.stdout.write(self.style.SUCCESS(
            f"Trading name overrides applied to {tn_applied} creditor row(s) "
            f"across {len(TRADING_NAMES_OVERRIDES)} mappings."
        ))

        for rep in ("WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS", "NONE"):
            self.stdout.write(f"  {rep}: {CreditorCriteria.objects.filter(representative=rep).count()} creditors")
        for source in ("GENERAL_CREDITOR", "REPRESENTATIVE", "DIVIDEND"):
            self.stdout.write(f"  Source {source}: {CreditorCriteria.objects.filter(source_sheet=source).count()} creditors")

        return {"created": created_count, "updated": updated_count, "skipped_manual": skipped_manual}
