from django.db import migrations


COUNTY_DISTRICTS = {
    'Buckinghamshire': [
        'South Bucks DC',
        'Chiltern DC',
        'Wycombe DC',
        'Aylesbury Vale DC',
        'Milton Keynes Council',
    ],
    'Cumbria': [
        'Barrow-in-Furness BC',
        'South Lakeland DC',
        'Copeland BC',
        'Allerdale BC',
        'Eden DC',
        'Carlisle CC',
    ],
    'Devon': [
        'Exeter CC',
        'Plymouth CC',
        'Torbay Council',
        'East Devon DC',
        'Mid Devon DC',
        'North Devon DC',
        'South Hams DC',
        'Teignbridge DC',
        'Torridge DC',
        'West Devon BC',
    ],
    'Essex': [
        'Basildon BC',
        'Braintree DC',
        'Brentwood BC',
        'Castle Point BC',
        'Chelmsford CC',
        'Colchester BC',
        'Epping Forest DC',
        'Harlow DC',
        'Maldon DC',
        'Rochford DC',
        'Tendring DC',
        'Uttlesford DC',
        'Southend-on-Sea BC',
        'Thurrock Council',
    ],
    'Gloucestershire': [
        'Cheltenham BC',
        'Cotswold DC',
        'Forest of Dean DC',
        'Gloucester CC',
        'Stroud DC',
        'Tewkesbury BC',
    ],
    'Hampshire': [
        'Basingstoke and Deane BC',
        'East Hampshire DC',
        'Eastleigh BC',
        'Fareham BC',
        'Gosport BC',
        'Hart DC',
        'Havant BC',
        'New Forest DC',
        'Rushmoor BC',
        'Test Valley BC',
        'Winchester CC',
        'Portsmouth CC',
        'Southampton CC',
        'Isle of Wight Council',
    ],
    'Hertfordshire': [
        'Broxbourne BC',
        'Dacorum BC',
        'East Hertfordshire DC',
        'Hertsmere BC',
        'North Hertfordshire DC',
        'St Albans CC',
        'Stevenage BC',
        'Three Rivers DC',
        'Watford BC',
        'Welwyn Hatfield BC',
    ],
    'Kent': [
        'Ashford BC',
        'Canterbury CC',
        'Dartford BC',
        'Dover DC',
        'Gravesham BC',
        'Maidstone BC',
        'Sevenoaks DC',
        'Shepway DC',
        'Swale BC',
        'Thanet DC',
        'Tonbridge and Malling BC',
        'Tunbridge Wells BC',
        'Medway Council',
    ],
    'Lancashire': [
        'Burnley BC',
        'Chorley BC',
        'Fylde BC',
        'Hyndburn BC',
        'Lancaster CC',
        'Pendle BC',
        'Preston CC',
        'Ribble Valley BC',
        'Rossendale BC',
        'South Ribble BC',
        'West Lancashire BC',
        'Wyre BC',
        'Blackburn with Darwen UA',
        'Blackpool UA',
    ],
    'Leicestershire': [
        'Blaby DC',
        'Charnwood BC',
        'Harborough DC',
        'Hinckley and Bosworth BC',
        'Melton BC',
        'North West Leicestershire DC',
        'Oadby and Wigston BC',
        'Leicester CC',
        'Rutland Council',
    ],
    'Lincolnshire': [
        'Boston BC',
        'East Lindsey DC',
        'Lincoln CC',
        'North Kesteven DC',
        'South Holland DC',
        'South Kesteven DC',
        'West Lindsey DC',
        'North Lincolnshire UA',
        'North East Lincolnshire UA',
    ],
    'Norfolk': [
        'Breckland DC',
        'Broadland DC',
        'Great Yarmouth BC',
        "King's Lynn and West Norfolk BC",
        'North Norfolk DC',
        'Norwich CC',
        'South Norfolk DC',
    ],
    'Northamptonshire': [
        'Corby BC',
        'Daventry DC',
        'East Northamptonshire DC',
        'Kettering BC',
        'Northampton BC',
        'South Northamptonshire DC',
        'Wellingborough BC',
    ],
    'Nottinghamshire': [
        'Ashfield DC',
        'Basford DC',
        'Broxtowe BC',
        'Gedling BC',
        'Mansfield DC',
        'Newark and Sherwood DC',
        'Rushcliffe BC',
        'Nottingham CC',
    ],
    'Oxfordshire': [
        'Cherwell DC',
        'Oxford CC',
        'South Oxfordshire DC',
        'Vale of White Horse DC',
        'West Oxfordshire DC',
    ],
    'Somerset': [
        'Mendip DC',
        'Sedgemoor DC',
        'South Somerset DC',
        'Taunton Deane BC',
        'West Somerset DC',
    ],
    'Suffolk': [
        'Babergh DC',
        'Forest Heath DC',
        'Ipswich BC',
        'Mid Suffolk DC',
        'St Edmundsbury BC',
        'Suffolk Coastal DC',
        'Waveney DC',
    ],
    'Surrey': [
        'Elmbridge BC',
        'Epsom and Ewell BC',
        'Guildford BC',
        'Mole Valley DC',
        'Reigate and Banstead BC',
        'Runnymede BC',
        'Spelthorne BC',
        'Surrey Heath BC',
        'Tandridge DC',
        'Waverley BC',
        'Woking BC',
    ],
    'Warwickshire': [
        'North Warwickshire BC',
        'Nuneaton and Bedworth BC',
        'Rugby BC',
        'Stratford-on-Avon DC',
        'Warwick DC',
    ],
    'West Sussex': [
        'Adur DC',
        'Arun DC',
        'Chichester DC',
        'Crawley BC',
        'Horsham DC',
        'Mid Sussex DC',
        'Worthing BC',
    ],
    'Worcestershire': [
        'Bromsgrove DC',
        'Malvern Hills DC',
        'Redditch BC',
        'Worcester CC',
        'Wychavon DC',
        'Wyre Forest DC',
    ],
    'Yorkshire (East Riding)': [
        'East Riding of Yorkshire Council',
        'Kingston upon Hull CC',
    ],
    # EXCEL_CRITERIA_REFERENCE.md — County Councils sheet
    'Cambridgeshire': [
        'Cambridge CC',
        'East Cambridgeshire DC',
        'Fenland DC',
        'Huntingdonshire DC',
        'South Cambridgeshire DC',
    ],
    # EXCEL_CRITERIA_REFERENCE.md — County Councils sheet
    'East Sussex': [
        'Eastbourne BC',
        'Hastings BC',
        'Lewes DC',
        'Rother DC',
        'Wealden DC',
    ],
}


def seed_phase2_data(apps, schema_editor):
    from datetime import date
    from decimal import Decimal

    CreditorCriteria = apps.get_model('debt_app', 'CreditorCriteria')
    CouncilRule = apps.get_model('debt_app', 'CouncilRule')
    CountyCouncilRouting = apps.get_model('debt_app', 'CountyCouncilRouting')
    DebtTypeCouncilVote = apps.get_model('debt_app', 'DebtTypeCouncilVote')
    ConditionalVoterRule = apps.get_model('debt_app', 'ConditionalVoterRule')
    CreditorOpenBankingRule = apps.get_model('debt_app', 'CreditorOpenBankingRule')

    reviewed = date(2025, 7, 1)

    # --- SECTION 1: Creditor seeds ---

    tbi, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='TBI Financial Services',
        defaults={
            'status': 'REJECT',
            'blocked_until_cleared': True,
            'blocked_reason': (
                'FCA complaint pending (Bamboo debt acquisition — contact Debra)'
            ),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        tbi.status = 'REJECT'
        tbi.blocked_until_cleared = True
        tbi.blocked_reason = (
            'FCA complaint pending (Bamboo debt acquisition — contact Debra)'
        )
        tbi.last_reviewed = reviewed
        tbi.save()

    moneybarn, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Moneybarn',
        defaults={
            'status': 'ACCEPT',
            'vehicle_arrears_repossession_months': 2,
            'fees_cap_percentage': Decimal('25.00'),
            'requires_arrangement_call_before_proposing': True,
            'reject_if_client_still_has_asset': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        moneybarn.status = 'ACCEPT'
        moneybarn.vehicle_arrears_repossession_months = 2
        moneybarn.fees_cap_percentage = Decimal('25.00')
        moneybarn.requires_arrangement_call_before_proposing = True
        moneybarn.reject_if_client_still_has_asset = True
        moneybarn.last_reviewed = reviewed
        moneybarn.save()

    bamboo, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Bamboo',
        defaults={
            'status': 'REJECT',
            'reject_if_never_made_payment': True,
            'reject_if_debt_repayable_within_months': 96,
            'reject_if_equity_exceeds_debt': True,
            'open_banking_access': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        bamboo.status = 'REJECT'
        bamboo.reject_if_never_made_payment = True
        bamboo.reject_if_debt_repayable_within_months = 96
        bamboo.reject_if_equity_exceeds_debt = True
        bamboo.open_banking_access = True
        bamboo.last_reviewed = reviewed
        bamboo.save()
    # Bamboo I&E maxed = MOD (not REJECT). Pending IEMatchChecker in Phase 6.
    # Not modelled as a hard block here.
    CreditorOpenBankingRule.objects.update_or_create(
        creditor=bamboo,
        defaults={
            'review_period_months': 3,
            'ie_must_match_exactly': True,
        },
    )

    vwfs, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Volkswagen Financial Services',
        defaults={
            'status': 'DO_NOT_VOTE',
            'termination_risk_if_vehicle_on_finance': True,
            'last_reviewed': reviewed,
            'trading_names': [
                'VW Financial Services',
                'Volkswagen Financial Services',
                'VWFS',
            ],
        },
    )
    if not _:
        vwfs.status = 'DO_NOT_VOTE'
        vwfs.termination_risk_if_vehicle_on_finance = True
        vwfs.last_reviewed = reviewed
        vwfs.trading_names = [
            'VW Financial Services',
            'Volkswagen Financial Services',
            'VWFS',
        ]
        vwfs.save()

    buddy, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Buddy Loans',
        defaults={
            'status': 'CONDITIONAL_VOTER',
            'conditional_voter': True,
            'conditional_voter_min_dividend_pence': 50,
            'last_reviewed': reviewed,
            'trading_names': [
                'Buddy Loans',
                'Advancis Ltd',
                'Buddy Loans t/a Advancis Ltd',
            ],
        },
    )
    if not _:
        buddy.status = 'CONDITIONAL_VOTER'
        buddy.conditional_voter = True
        buddy.conditional_voter_min_dividend_pence = 50
        buddy.last_reviewed = reviewed
        buddy.trading_names = [
            'Buddy Loans',
            'Advancis Ltd',
            'Buddy Loans t/a Advancis Ltd',
        ]
        buddy.save()
    ConditionalVoterRule.objects.update_or_create(
        creditor=buddy,
        defaults={
            'min_dividend_pence': 50,
            'contact_required': False,
        },
    )

    salary, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Salary Finance',
        defaults={
            'status': 'CONDITIONAL_VOTER',
            'conditional_voter': True,
            'conditional_voter_min_dividend_pence': None,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        salary.status = 'CONDITIONAL_VOTER'
        salary.conditional_voter = True
        salary.conditional_voter_min_dividend_pence = None
        salary.last_reviewed = reviewed
        salary.save()
    ConditionalVoterRule.objects.update_or_create(
        creditor=salary,
        defaults={
            'min_dividend_pence': None,
            'contact_required': True,
        },
    )

    commsave, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Commsave Credit Union',
        defaults={
            'status': 'WILL_CONSIDER',
            'reject_if_in_dmp': True,
            'reject_if_majority_share_exceeds_pct': Decimal('50.00'),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        commsave.status = 'WILL_CONSIDER'
        commsave.reject_if_in_dmp = True
        commsave.reject_if_majority_share_exceeds_pct = Decimal('50.00')
        commsave.last_reviewed = reviewed
        commsave.save()

    cambrian, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='CAMBRIAN Credit Union',
        defaults={
            'status': 'WILL_CONSIDER',
            'reject_if_in_dmp': True,
            'reject_if_debt_repayable_within_months': 6,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        cambrian.status = 'WILL_CONSIDER'
        cambrian.reject_if_in_dmp = True
        cambrian.reject_if_debt_repayable_within_months = 6
        cambrian.last_reviewed = reviewed
        cambrian.save()

    amigo, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Amigo Loans',
        defaults={
            'status': 'DO_NOT_VOTE',
            'blocked_until_cleared': False,
            'blocked_reason': (
                'In redress scheme July 2024 — DO NOT VOTE. '
                'When active: <12m+evidenced=50p; >12m+evidenced=30p; '
                'no evidence=REJECT; repayable<84m=REJECT'
            ),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        amigo.status = 'DO_NOT_VOTE'
        amigo.blocked_until_cleared = False
        amigo.blocked_reason = (
            'In redress scheme July 2024 — DO NOT VOTE. '
            'When active: <12m+evidenced=50p; >12m+evidenced=30p; '
            'no evidence=REJECT; repayable<84m=REJECT'
        )
        amigo.last_reviewed = reviewed
        amigo.save()

    plata, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Plata Loans',
        defaults={
            'status': 'WILL_CONSIDER',
            'reject_if_majority_share_exceeds_pct': Decimal('85.00'),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        plata.status = 'WILL_CONSIDER'
        plata.reject_if_majority_share_exceeds_pct = Decimal('85.00')
        plata.last_reviewed = reviewed
        plata.save()

    copperpot, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='No1 Copperpot Credit Union',
        defaults={
            'status': 'REJECT',
            'reject_if_police_employed': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        copperpot.status = 'REJECT'
        copperpot.reject_if_police_employed = True
        copperpot.last_reviewed = reviewed
        copperpot.save()

    penny, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Penny Post Credit Union',
        defaults={
            'status': 'REJECT',
            'last_reviewed': reviewed,
        },
    )
    if not _:
        penny.status = 'REJECT'
        penny.last_reviewed = reviewed
        penny.save()

    slc, _ = CreditorCriteria.objects.get_or_create(
        creditor_name='Student Loans Company',
        defaults={
            'status': 'WILL_CONSIDER',
            'requires_grant_overpayment_only': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        slc.status = 'WILL_CONSIDER'
        slc.requires_grant_overpayment_only = True
        slc.last_reviewed = reviewed
        slc.save()

    # --- SECTION 2: Council seeds ---

    # EXCEL_CRITERIA_REFERENCE.md — Councils sheet
    slough, _ = CouncilRule.objects.get_or_create(
        council_name='Slough Borough Council',
        defaults={
            'status': 'REJECT',
            'do_not_chase': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        slough.status = 'REJECT'
        slough.do_not_chase = True
        slough.last_reviewed = reviewed
        slough.save()

    shropshire, _ = CouncilRule.objects.get_or_create(
        council_name='Shropshire Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'last_reviewed': reviewed,
        },
    )
    if not _:
        shropshire.status = 'WILL_CONSIDER'
        shropshire.last_reviewed = reviewed
        shropshire.save()
    DebtTypeCouncilVote.objects.get_or_create(
        council=shropshire,
        debt_type='COUNCIL_TAX',
        defaults={'status': 'REJECT'},
    )
    DebtTypeCouncilVote.objects.get_or_create(
        council=shropshire,
        debt_type='PCN',
        defaults={'status': 'WILL_CONSIDER'},
    )

    huntingdon, _ = CouncilRule.objects.get_or_create(
        council_name='Huntingdonshire District Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'reject_if_benefits_only': True,
            'reject_if_any_benefits': True,
            'reject_if_joint_one_party_only': True,
            'reject_if_previous_iva': True,
            'reject_if_dro_criteria_met': True,
            'reject_if_aoe_in_place': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        huntingdon.status = 'WILL_CONSIDER'
        huntingdon.reject_if_benefits_only = True
        huntingdon.reject_if_any_benefits = True
        huntingdon.reject_if_joint_one_party_only = True
        huntingdon.reject_if_previous_iva = True
        huntingdon.reject_if_dro_criteria_met = True
        huntingdon.reject_if_aoe_in_place = True
        huntingdon.last_reviewed = reviewed
        huntingdon.save()

    doncaster, _ = CouncilRule.objects.get_or_create(
        council_name='Doncaster Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'reject_if_employed': True,
            'reject_if_unemployed_and_homeowner': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        doncaster.status = 'WILL_CONSIDER'
        doncaster.reject_if_employed = True
        doncaster.reject_if_unemployed_and_homeowner = True
        doncaster.last_reviewed = reviewed
        doncaster.save()

    cardiff, _ = CouncilRule.objects.get_or_create(
        council_name='Cardiff Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'blocked_reason': (
                'Always include current CT year regardless of balance'
            ),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        cardiff.status = 'WILL_CONSIDER'
        cardiff.blocked_reason = (
            'Always include current CT year regardless of balance'
        )
        cardiff.last_reviewed = reviewed
        cardiff.save()

    walsall, _ = CouncilRule.objects.get_or_create(
        council_name='Walsall Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'blocked_reason': (
                'Always include current CT year regardless of balance'
            ),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        walsall.status = 'WILL_CONSIDER'
        walsall.blocked_reason = (
            'Always include current CT year regardless of balance'
        )
        walsall.last_reviewed = reviewed
        walsall.save()

    waltham, _ = CouncilRule.objects.get_or_create(
        council_name='Waltham Forest Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'blocked_reason': (
                'Always include current CT year regardless of balance'
            ),
            'last_reviewed': reviewed,
        },
    )
    if not _:
        waltham.status = 'WILL_CONSIDER'
        waltham.blocked_reason = (
            'Always include current CT year regardless of balance'
        )
        waltham.last_reviewed = reviewed
        waltham.save()

    colchester, _ = CouncilRule.objects.get_or_create(
        council_name='Colchester Borough Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'min_dividend_pence': 45,
            'source_priority': 1,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        colchester.status = 'WILL_CONSIDER'
        colchester.min_dividend_pence = 45
        colchester.source_priority = 1
        colchester.last_reviewed = reviewed
        colchester.save()

    southwark, _ = CouncilRule.objects.get_or_create(
        council_name='Southwark Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'last_reviewed': reviewed,
        },
    )
    if not _:
        southwark.status = 'WILL_CONSIDER'
        southwark.last_reviewed = reviewed
        southwark.save()
    DebtTypeCouncilVote.objects.get_or_create(
        council=southwark,
        debt_type='PCN',
        defaults={'status': 'ACCEPT'},
    )
    DebtTypeCouncilVote.objects.get_or_create(
        council=southwark,
        debt_type='COUNCIL_TAX',
        defaults={'status': 'REJECT'},
    )

    lewisham, _ = CouncilRule.objects.get_or_create(
        council_name='Lewisham Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'last_reviewed': reviewed,
        },
    )
    if not _:
        lewisham.status = 'WILL_CONSIDER'
        lewisham.last_reviewed = reviewed
        lewisham.save()
    DebtTypeCouncilVote.objects.get_or_create(
        council=lewisham,
        debt_type='COUNCIL_TAX',
        defaults={'status': 'REJECT'},
    )
    DebtTypeCouncilVote.objects.get_or_create(
        council=lewisham,
        debt_type='PCN',
        defaults={'status': 'DO_NOT_VOTE'},
    )

    durham, _ = CouncilRule.objects.get_or_create(
        council_name='Durham Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'last_reviewed': reviewed,
        },
    )
    if not _:
        durham.status = 'WILL_CONSIDER'
        durham.last_reviewed = reviewed
        durham.save()
    DebtTypeCouncilVote.objects.get_or_create(
        council=durham,
        debt_type='HOUSING_BENEFIT',
        defaults={'status': 'DO_NOT_VOTE'},
    )
    DebtTypeCouncilVote.objects.get_or_create(
        council=durham,
        debt_type='COUNCIL_TAX',
        defaults={'status': 'REJECT'},
    )

    portsmouth, _ = CouncilRule.objects.get_or_create(
        council_name='Portsmouth City Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'last_reviewed': reviewed,
        },
    )
    if not _:
        portsmouth.status = 'WILL_CONSIDER'
        portsmouth.last_reviewed = reviewed
        portsmouth.save()
    DebtTypeCouncilVote.objects.get_or_create(
        council=portsmouth,
        debt_type='PCN',
        defaults={'status': 'DO_NOT_VOTE'},
    )
    DebtTypeCouncilVote.objects.get_or_create(
        council=portsmouth,
        debt_type='COUNCIL_TAX',
        defaults={'status': 'REJECT'},
    )

    mid_suffolk, _ = CouncilRule.objects.get_or_create(
        council_name='Mid Suffolk District Council',
        defaults={
            'status': 'WILL_CONSIDER',
            'reject_if_employed': True,
            'last_reviewed': reviewed,
        },
    )
    if not _:
        mid_suffolk.status = 'WILL_CONSIDER'
        mid_suffolk.reject_if_employed = True
        mid_suffolk.last_reviewed = reviewed
        mid_suffolk.save()

    # --- SECTION 3: County council routing seeds ---

    for county_name, districts in COUNTY_DISTRICTS.items():
        for district_name in districts:
            CountyCouncilRouting.objects.get_or_create(
                county_name=county_name,
                district_name=district_name,
                defaults={'council_rule': None},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0009_phase2_schema'),
    ]

    operations = [
        migrations.RunPython(seed_phase2_data, migrations.RunPython.noop),
    ]
