import os, sys, json, django
from datetime import date, timedelta

# Add project root to sys.path so debt_project is importable when running the script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.criteria_engine import assess_case

payloads_path = r'C:\Users\Canton Computers\Desktop\case-assessment-staging\case-assessment-backend\test_payloads.json'

# Dates that will always pass document checks
RECENT_BANK_DATE  = (date.today() - timedelta(days=30)).isoformat()  # 30 days ago
RECENT_PAYSLIP    = (date.today() - timedelta(days=14)).isoformat()  # 14 days ago
_STALE_CUTOFF     = (date.today() - timedelta(days=89)).isoformat()  # TIG-11 rejects >90 days

def clean_payload(case):
    """Fix payload issues that block every case regardless of business logic."""

    # Fix 1: ensure bank statement has a recent valid date
    has_bank = False
    has_payslip = False
    for doc in case.get("documents", []):
        if doc["document_type"] == "bank_statement":
            has_bank = True
            ed = doc.setdefault("extracted_data", {})
            # Fill missing date or refresh stale dates (>89 days old triggers TIG-11)
            if not ed.get("statement_date") or ed["statement_date"] < _STALE_CUTOFF:
                ed["statement_date"] = RECENT_BANK_DATE
            if not ed.get("account_holder"):
                ed["account_holder"] = case["client_name"]
        if doc["document_type"] in ("payslip", "income_proof"):
            has_payslip = True
            ed = doc.setdefault("extracted_data", {})
            if not ed.get("statement_date"):
                ed["statement_date"] = RECENT_PAYSLIP

    # Fix 2: add payslip if employed and missing
    if case.get("is_employed") and not has_payslip:
        case["documents"].append({
            "document_type": "payslip",
            "is_valid": True,
            "extracted_data": {"statement_date": RECENT_PAYSLIP}
        })

    # Fix 3: add bank statement if completely missing
    if not has_bank:
        case["documents"].append({
            "document_type": "bank_statement",
            "is_valid": True,
            "extracted_data": {
                "statement_date": RECENT_BANK_DATE,
                "account_holder": case["client_name"]
            }
        })

    return case


with open(payloads_path) as f:
    cases = json.load(f)

# Creditor name map — Aryza full names → DB canonical names
CREDITOR_NAME_MAP = {
    "The Very Group Limited (WPM)":                     "Very",
    "Lendable Limited t/a Zable":                       "Zable",
    "Lendable Limited t/a AutoLend":                    "Lendable",
    "Capital One Bank (Europe) Plc":                    "Capital One",
    "Gracombex Ltd t/a The Money Platform":             "The Money Platform",
    "Gracombex LTD T/A The Money Platform":             "The Money Platform",
    "Madison Cf Uk LTD T/A 118 118 Money":              "118 118 Money",
    "Natwest Group Plc":                                "NatWest",
    "Lloyds Bank Plc":                                  "Lloyds Bank",
    "JD Williams (N Brown Group Plc)":                  "JD Williams",
    "Link Financial Ltd":                               "Link Financial",
    "Link Financial Outsourcing Limited":               "Link Financial",
    "Link Financial Outsourcing Limited":               "Link Financial",
    "Lantern Debt Recovery Services Ltd":               "Lantern",
    "Perch Capital Limited":                            "Perch Capital",
    "Brighton & Hove City Council":                     "Brighton and Hove City Council",
    "North East Lincolnshire Borough Council":          "North East Lincolnshire Council",
    "Mansfield District Council":                       "Mansfield District Council",
    "West Sussex & Surrey Credit Union Limited t/a Boom Community Bank": "Boom Credit Union",
    "Bamboo Limited (Link Financial)":                  "Bamboo",
    "Fairscore Limited t/a Updraft":                    "Updraft",
    "PRA Group (UK) Ltd c/o WPM":                      "PRA Group",
    "PRA Group (UK) Limited (TIX)":                    "PRA Group",
    "Cabot Financial (Europe) Ltd":                     "Cabot Financial",
    "Cabot Credit Management Group Limited":            "Cabot Financial",
    "Department for Work & Pensions (DWP)":             "DWP",
    "Lowell Financial":                                 "Lowell",
    "Lowell Portfolio I Ltd":                           "Lowell",
    "Lowell Portfolio I LTD":                           "Lowell",
    "American Express Services Europe Ltd":             "American Express",
    "HM Revenue & Customs":                             "HMRC",
    "Northridge Finance Ltd":                           "Northridge Finance",
    "Blue Motor Finance Limited":                       "Blue Motor Finance",
    "Home retail group":                                "Argos",
    "Zilch Technology Limited":                         "Zilch",
    "Zopa Bank Limited":                                "Zopa",
    "NewDay Limited":                                   "NewDay",
    "Vanquis Bank Limited":                             "Vanquis",
    "Klarna UK Ltd":                                    "Klarna",
    "Klarna Pay Later And Pay In 3":                    "Klarna",
    "TSB Bank Plc":                                     "TSB",
    "Monzo Bank":                                       "Monzo",
    "Barclays Bank Plc":                                "Barclays",
    "Halifax":                                          "Halifax",
    "Nationwide Building Society":                      "Nationwide",
    "Castle Community Bank":                            "Castle Community Bank",
    "Advanced Payment Solutions Ltd t/a Cashplus Bank": "Cashplus",
    "Zempler Bank Limited":                             "Cashplus",
    "MBNA Limited":                                     "MBNA",
    "Salary Finance":                                   "Salary Finance",
    "118 118 Money":                                    "118 118 Money",
    "Updraft":                                          "Updraft",
    "CCC Debt Management":                              "CCC Debt Management",
    "United Trust Bank Limited":                        "United Trust Bank",
    "Octopus Energy Limited":                           "Octopus Energy",
    "British Gas Consumer":                             "British Gas",
    "Black Horse Limited":                              "Black Horse",
    "Anderson Brookes":                                 "Anderson Brookes",
    "CREDIT4 LIMITED":                                  "Credit4",
    "TRAVIS PERKINS PLC":                               "Travis Perkins",
    "TYRELL CARPENTRY CONTRACTORS LIMITED":             "Tyrell Carpentry",
    "Huws Gray Builders Merchant":                      "Huws Gray",
    "Creation Consumer Finance":                        "Creation Finance",
    "Creation Consumer Finance LTD":                    "Creation Finance",
}

def normalise_creditor_names(case):
    for c in case.get("creditors", []):
        original = c["creditor_name"]
        c["creditor_name"] = CREDITOR_NAME_MAP.get(original, original)
    return case


for case in cases:
    meta = case.pop("_meta")
    case_num = meta["case"]
    source   = meta["source"]

    if "client_name" not in case:
        print(f"\n=== CASE {case_num} — {source} SKIPPED ===")
        continue

    case = clean_payload(case)
    case = normalise_creditor_names(case)

    result = assess_case(case)

    status = result.get("overall_status")
    hard_blocks = [r for r in result.get("hard_blocks", []) if "triggered=True" in str(r)]
    flags       = [r for r in result.get("flags", [])       if "triggered=True" in str(r)]

    def extract_ids(rule_list):
        ids = []
        for r in rule_list:
            s = str(r)
            start = s.find("rule_id='") + 9
            end   = s.find("'", start)
            if start > 8:
                ids.append(s[start:end])
        return ids

    maj = result.get("majority_analysis", {})
    unknown = [
        p["creditor_name"]
        for p in result.get("creditor_positions", [])
        if p.get("effective_status") == "UNKNOWN"
    ]

    print(f"\n=== CASE {case_num} — {case['client_name']} ===")
    print(f"  Source      : {source}")
    print(f"  Status      : {status}")
    print(f"  Hard blocks : {extract_ids(hard_blocks)}")
    print(f"  Flags       : {extract_ids(flags)}")
    print(f"  Majority    : achievable={maj.get('achievable')}  "
          f"voting={maj.get('voting_debt')}/{maj.get('total_debt')}")
    if unknown:
        print(f"  UNKNOWN creds ({len(unknown)}): {unknown}")