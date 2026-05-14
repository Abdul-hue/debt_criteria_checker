You are a senior Django backend engineer completing a UK debt criteria checker.
The engine (criteria_engine.py) is fully implemented and tested — 53/53 tests pass.
Do NOT modify any rule logic. Your job is wiring only.

Complete these two tasks in order. Confirm each before moving to the next.

═══════════════════════════════════════════════
TASK 6A — Seed CreditorCriteria with representatives
═══════════════════════════════════════════════

The engine's detect_representatives() function queries:

    CreditorCriteria.objects.filter(
        creditor_name__in=names,
        representative__isnull=False,
    ).values_list("representative", flat=True)

This returns empty in production because no creditor names are
seeded against WATCH/TIX/EVOLVE representatives.

Create a management command:
    debt_app/management/commands/seed_creditor_criteria.py

Seed these creditors with their representatives.
Use update_or_create keyed on creditor_name.

WATCH creditors (representative="WATCH"):
  Barclays, Barclaycard, Barclays Direct, Woolwich,
  MBNA, Virgin Money, Tesco Bank, Capital One,
  Aqua, Marbles, Fluid, Opus

TIX creditors (representative="TIX"):
  Shop Direct, Very, Littlewoods, Littlewoods.com,
  Creation, Creation Consumer Finance, Sygma, Laser,
  NewDay, Aquis, Blemain

EVOLVE creditors (representative="EVOLVE"):
  NatWest, Royal Bank of Scotland, Ulster Bank,
  Coutts, Think Banking, Lombard

Also seed the 12 banking groups into parent_group field.
Use this exact group mapping:

  RBS Group:        Royal Bank of Scotland, NatWest,
                    Ulster Bank, Coutts, Think Banking
  Lloyds Group:     Lloyds, Bank of Scotland, Halifax,
                    Blackhorse, Birmingham Midshires,
                    AA, Intelligent Finance,
                    Cheltenham and Gloucester, Saga
  Barclays Group:   Barclays, Barclays Direct,
                    Barclaycard, Woolwich, Standard Life
  HSBC Group:       HSBC, First Direct, Midland Bank
  Santander Group:  Santander, Cahoot,
                    Alliance and Leicester, Abbey National
  Co-op Group:      Co-operative Bank, Smile,
                    Britannia Building Society
  BoI Group:        Bank of Ireland, Post Office
  Nationwide Group: Nationwide, Cheshire BS,
                    Derbyshire BS, Dunfermline BS
  Yorkshire Group:  Yorkshire BS, Barnsley BS,
                    Chelsea BS, Norwich and Peterborough BS
  Clydesdale Group: Clydesdale Bank, Yorkshire Bank,
                    National Australia
  Skipton Group:    Skipton BS, Chesham BS, Scarborough BS
  Coventry Group:   Coventry BS, Stroud and Swindon BS
  Shop Direct Group: Shop Direct, Very,
                     Littlewoods, Littlewoods.com

After seeding, verify with:
    python manage.py shell -c "
    from debt_app.models import CreditorCriteria
    print(CreditorCriteria.objects.filter(
        representative='WATCH').count(), 'WATCH creditors')
    print(CreditorCriteria.objects.filter(
        representative='TIX').count(), 'TIX creditors')
    print(CreditorCriteria.objects.filter(
        representative='EVOLVE').count(), 'EVOLVE creditors')
    "

═══════════════════════════════════════════════
TASK 6B — Django REST API view
═══════════════════════════════════════════════

Create a POST endpoint at /api/v1/assess/

The view must:
1. Accept JSON body matching the case assessment payload format
2. Call detect_representatives(case_json["creditors"])
3. Call assess_case(case_json, detected_representatives)
4. Return JSON response in this exact structure:

{
  "overall": "blocked" | "flagged" | "pass",
  "representatives_detected": ["WATCH", "TIX"],
  "summary": {
    "hard_block_count": 2,
    "flag_count": 3,
    "info_count": 1,
    "passed_count": 40
  },
  "hard_blocks": [
    {
      "rule_id": "TIG-01",
      "severity": "hard_block",
      "triggered": true,
      "message": "Total debt £5,500 is below the £6,000 minimum.",
      "threshold": 6000.0,
      "actual_value": 5500.0
    }
  ],
  "flags": [...],
  "info": [...],
  "passed": [...]
}

Error handling:
- Missing or invalid JSON body → 400 with {"error": "Invalid JSON"}
- assess_case() raises exception → 500 with {"error": "Engine error", "detail": str(e)}
- Any other exception → 500

The view must NOT use Django REST Framework if it is not
already installed. Use JsonResponse and json.loads only.
If DRF is already installed, use an APIView.

Add the URL to urls.py.

After implementing, test with:
    python manage.py runserver

Then in a second terminal:
    curl -X POST http://127.0.0.1:8000/api/v1/assess/ \
      -H "Content-Type: application/json" \
      -d "{\"crm_data\": {\"total_unsecured_debt\": 5000},
           \"financial_summary\": {\"net_balance\": 50,
             \"total_income\": 2000, \"income_source\": \"payslip\",
             \"documents\": {}},
           \"creditors\": [],
           \"gold_transactions\": [],
           \"mortgage_details\": [],
           \"evidence_ledger\": [],
           \"documents\": [],
           \"clientInfo\": {\"dateOfBirth\": \"1980-01-01\"},
           \"has_property\": false,
           \"has_job\": true,
           \"has_uc_journal\": false}"

Expected response: overall="blocked",
TIG-01 and TIG-02 both in hard_blocks.

═══════════════════════════════════════════════
RULES FOR THIS SESSION
═══════════════════════════════════════════════
1. Do not touch criteria_engine.py rule logic
2. Do not change GlobalCriteria seed data
3. Do not add rules not in the source documents
4. RuleResult is a dataclass — serialise with dataclasses.asdict()
5. detected_representatives is a set — serialise as sorted list
6. Paste the complete file for every file you create or modify