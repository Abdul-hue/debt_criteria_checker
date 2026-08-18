"""
Seed CreditorCriteria with representative and parent_group data.

Source of truth: Which_Representative_Criteria.md
Run with: python manage.py seed_creditor_criteria [--dry-run]
"""

import os
import re
from django.conf import settings
from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria
from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name

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
    "Admiral Loans": {"account_age_months": 3,                        # "running cases: 3 months or older"
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
    "Loans by Mal": {"account_age_months": 3,                        # "REJECT IF LESS THAN 3 MONTHS"
                     "reject_if_debt_repayable_within_months": 84,   # "REPAID IN 84 MONTHS"
                     "reject_if_ie_doesnt_match_application": True}, # "APPLICATION DOES NOT MATCH OUR I&E"
    "Loans 2 Go": {"account_age_months": 1,                          # "if loan less than 1 month old"
                   "reject_if_never_made_payment": True,             # "reject if no payment has been made"
                   "fraud_claim_risk": True},                        # "reject and claim fraud"
    "Mutual Clothing": {"account_age_months": 6},                    # "IF TAKEN OUT RECENTLY WILL REJECT (6 MONTHS)"
    "One Stop Money Shop": {"account_age_months": 3},                # "LESS THAN 3 MONTHS OLD"
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
    "HM Revenue & Customs": {"reject_if_equity_exceeds_debt": True},       # "WILL REJECT if more equity than their debt"
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
        "min_dividend_pence": 50,                              # Dividends: "Guarantor My Loan: 50p" — name differs
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


class Command(BaseCommand):
    help = "Strict sync CreditorCriteria with General and Representative Excel sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be changed without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            valid_map = _parse_strict_sources()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error parsing sources: {e}"))
            return

        # 1. Remove non-creditors (orphans not in General or Rep files)
        db_creditors = CreditorCriteria.objects.all()
        deleted_count = 0
        for c in db_creditors:
            if c.creditor_name not in valid_map:
                if dry_run:
                    self.stdout.write(self.style.WARNING(f"  [DELETE] {c.creditor_name}"))
                else:
                    c.delete()
                deleted_count += 1

        # 2. Upsert valid ones
        created_count = 0
        updated_count = 0

        for name, data in sorted(valid_map.items()):
            defaults = {
                "representative": data["representative"],
                "source_sheet": data["source"],
                "is_active": True,
                "trading_names": data["trading_names"],
                "min_dividend_pence": data["min_dividend_pence"],
                "dividend_notes": data["dividend_notes"],
            }
            if data["parent_group"]:
                defaults["parent_group"] = data["parent_group"]
            if "status" in data and data["status"]:
                defaults["status"] = data["status"]
            if "criteria_notes" in data and data["criteria_notes"]:
                defaults["criteria_notes"] = data["criteria_notes"]
            if "contact_phone" in data and data["contact_phone"]:
                defaults["contact_phone"] = data["contact_phone"]
            if "contact_email" in data and data["contact_email"]:
                defaults["contact_email"] = data["contact_email"]
            if "contact_name" in data and data["contact_name"]:
                defaults["contact_name"] = data["contact_name"]
            if "raw_updated_criteria" in data and data["raw_updated_criteria"]:
                defaults["raw_updated_criteria"] = data["raw_updated_criteria"]

            if dry_run:
                continue

            _, created = CreditorCriteria.objects.update_or_create(
                creditor_name=name,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nDry run complete. Would delete {deleted_count} and sync {len(valid_map)} creditors."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Strict Sync complete. Deleted: {deleted_count}  Created: {created_count}  Updated: {updated_count}"
        ))

        # 3. Apply structured conditional criteria (engine-consumed fields).
        # Runs after the prose import so it is reseed-safe.
        # Only sets fields that are still at their unset default (None / False).
        # If a field has been manually edited in Django admin, it is preserved.
        # Case-insensitive name match; warns on any unmatched name.
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
                    # Treat None and False as "never set" — preserve any other manual value.
                    if current is None or current is False:
                        patch[field] = value
                    else:
                        skipped += 1
                        self.stdout.write(
                            f"  [STRUCTURED] {obj.creditor_name}.{field} = {current!r} "
                            f"(manually set, seed value {value!r} skipped)"
                        )
                if patch:
                    CreditorCriteria.objects.filter(pk=obj.pk).update(**patch)
                    applied += 1
        self.stdout.write(self.style.SUCCESS(
            f"Structured criteria applied to {applied} creditor row(s) "
            f"across {len(STRUCTURED_CRITERIA)} mappings "
            f"({skipped} field(s) skipped — already set in DB)."
        ))

        # 4. Apply trading name overrides — reseed-safe for the same reason as
        # STRUCTURED_CRITERIA (see comment on TRADING_NAMES_OVERRIDES above).
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
            count = CreditorCriteria.objects.filter(representative=rep).count()
            self.stdout.write(f"  {rep}: {count} creditors")
        
        for source in ("GENERAL_CREDITOR", "REPRESENTATIVE", "DIVIDEND"):
            count = CreditorCriteria.objects.filter(source_sheet=source).count()
            self.stdout.write(f"  Source {source}: {count} creditors")
