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
    "Clockwise Credit Union": {"account_age_months": 2},             # "loan taken out in last 8 weeks" (8wk≈2mo)
    "Everyday Loans": {"account_age_months": 6,                      # "Loan must be 6 months old"
                       "reject_if_debt_repayable_within_months": 120},  # "cannot be debt repayment in 10 years"
    "Fair for you Enterprise": {"account_age_months": 1},            # "NO LESS THAN 30 DAYS OLD"
    "Hitachi Capital/Credit / Novuna": {"account_age_months": 1},    # "reject if taken out in less than 1 month"
    "Ikano Finance": {"account_age_months": 12},                     # "if under a year old"
    "Loans at home": {"account_age_months": 1},                      # "if loan taken out in last 1 months"
    "Loans by Mal": {"account_age_months": 3,                        # "REJECT IF LESS THAN 3 MONTHS"
                     "reject_if_debt_repayable_within_months": 84},  # "REPAID IN 84 MONTHS"
    "Loans 2 Go": {"account_age_months": 1,                          # "if loan less than 1 month old"
                   "fraud_claim_risk": True},                        # "reject and claim fraud"
    "Mutual Clothing": {"account_age_months": 6},                    # "IF TAKEN OUT RECENTLY WILL REJECT (6 MONTHS)"
    "One Stop Money Shop": {"account_age_months": 3},                # "LESS THAN 3 MONTHS OLD"
    "Savvy (TICK TOCK LOANS)": {"account_age_months": 6,             # "IF LOAN IS LESS THAN 6 MONTHS OLD"
                                "fraud_claim_risk": True},           # "CALL OUT FRAUD"
    "Transave UK Credit Union": {"account_age_months": 3},           # "needs to be at least 3 months old"
    "UK Credit Ltd": {"account_age_months": 6},                      # "WILL REJECT IF LOAN IS UNDER 6 MONTHS"
    "Wiltshire and Swindon Credit Union": {"account_age_months": 6}, # "reject if less than 6 months old"

    # --- debt repayable within N months (balance/DI < N → reject) ---
    "Lifestyle Loans": {"reject_if_debt_repayable_within_months": 80},   # "repaid in 80 months"
    "Hastings Direct Loans": {"reject_if_debt_repayable_within_months": 120},  # "repayed in 10 years"

    # --- equity > debt (homeowner, 85% LTV) → reject ---
    "American Express Service": {"reject_if_equity_exceeds_debt": True},   # "REJECT IF MORE EQUITY THAN THEIR DEBT"
    "HM Revenue & Customs": {"reject_if_equity_exceeds_debt": True},       # "WILL REJECT if more equity than their debt"
    "Shawbrook": {"reject_if_equity_exceeds_debt": True},                  # "MORE EQUTIY THEN THERE DEBT WILL REJECT"
    "The Funding Corporation": {"reject_if_equity_exceeds_debt": True},    # "reject if more equity than their debt"
    "Funding Circle": {"reject_if_equity_exceeds_debt": True},             # "WILL REJECT IF EQUITY IN PROPERTY"
    "IWOCA / IWOKA LOANS": {"reject_if_equity_exceeds_debt": True,         # "cannot be more equity than their debt"
                            "requires_pg_called_up": True},                # "PG must have been called up"

    # --- majority share % → reject ---
    "Commsave Credit Union": {"reject_if_majority_share_exceeds_pct": 50,  # "Reject if they own over 50%"
                              "reject_if_in_dmp": True,                    # "REJECT IF CLIENT IS IN DMP"
                              "min_dividend_pence": 50},                   # "looks like will accept around 50p"
    "Plata Loans (BAMBOO)": {"reject_if_majority_share_exceeds_pct": 85},  # "more then 85% then they will reject"

    # --- financed asset must be returned → reject (dormant unless payload signal) ---
    "Advantage Finance": {"reject_if_client_still_has_asset": True,        # "Car needs to have gone back"
                          "reject_if_ccj": True, "reject_if_aoe": True},   # "REJECT IF ... AOE OR CCJ"
    "First Response Finance": {"reject_if_client_still_has_asset": True},  # "car needs to have gone back"
    "Marsh Finance": {"reject_if_client_still_has_asset": True},           # "car had to have gone back"
    "Oodle Finance": {"reject_if_client_still_has_asset": True},           # "MUST HAVE THE VEHICLE IN THEIR POSSESSION"
    "Snap on Tools": {"reject_if_client_still_has_asset": True},           # "REJECT IF CUSTOMER STILL HAS TOOLS"
    "Moneybarn": {"reject_if_client_still_has_asset": True,                # "CAR MUST HAVE BEEN RETURNED ... OTHERWISE REJECT"
                  "fees_cap_percentage": 25},                             # "fees capped at 25% of TR"

    # --- flags ---
    "South Yorkshire Credit Union": {"fraud_claim_risk": True},           # "reject if taken out fraudulently"
    "Unify Credit Union Limited": {"fraud_claim_risk": True},             # "THEY ALSO CLAIM FRAUD"
    "No1 Copperpot Credit Union": {"reject_if_police_employed": True},    # "CANNOT INCLUDE IF STILL EMLOYED BY THE POLICE"
    "Volkswagen Financial Services": {"termination_risk_if_vehicle_on_finance": True},  # "will terminate ... if car is on finance"
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
        # Runs after the prose import so it is authoritative and reseed-safe.
        # Case-insensitive match; warns (does not fail) on any unmatched name so a
        # renamed/removed creditor is surfaced rather than silently skipped.
        applied = 0
        for crit_name, fields in STRUCTURED_CRITERIA.items():
            matched = CreditorCriteria.objects.filter(creditor_name__iexact=crit_name).update(**fields)
            if matched:
                applied += matched
            else:
                self.stdout.write(self.style.WARNING(
                    f"  [STRUCTURED] no creditor matched '{crit_name}' — criteria not applied"
                ))
        self.stdout.write(self.style.SUCCESS(
            f"Structured criteria applied to {applied} creditor row(s) "
            f"across {len(STRUCTURED_CRITERIA)} mappings."
        ))

        for rep in ("WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS", "NONE"):
            count = CreditorCriteria.objects.filter(representative=rep).count()
            self.stdout.write(f"  {rep}: {count} creditors")
        
        for source in ("GENERAL_CREDITOR", "REPRESENTATIVE", "DIVIDEND"):
            count = CreditorCriteria.objects.filter(source_sheet=source).count()
            self.stdout.write(f"  Source {source}: {count} creditors")
