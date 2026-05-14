import sys
sys.path.insert(0, 'debt_app')

from criteria_engine import (
    _tig_01, _tig_20, _tig_20_1,
    _watch_22_5, _watch_22_8, _watch_22_10,
    _tix_04, _tig_15_8, _tig_15_9,
    _parse_case,
)
from datetime import date


def base():
    return {
        'crm_data': {'total_unsecured_debt': 7000},
        'financial_summary': {
            'net_balance': 700, 'total_income': 2500,
            'income_source': 'payslip', 'documents': {},
        },
        'creditors': [
            {'creditor_name': 'Barclays', 'balance': '4000', 'creditor_type': 'unsecured_loan'},
            {'creditor_name': 'HMRC',     'balance': '3000', 'creditor_type': 'unsecured_loan'},
        ],
        'gold_transactions': [],
        'mortgage_details': [],
        'evidence_ledger': [],
        'documents': [{
            'document_type': 'bank_statement',
            'is_valid': True,
            'extracted_data': {
                'account_holder': 'John',
                'statement_date': date.today().isoformat(),
            },
        }],
        'clientInfo': {'dateOfBirth': '1980-01-01'},
        'has_property': False,
        'has_job': True,
        'has_uc_journal': False,
    }


c = _parse_case(base())

checks = [
    ('TIG-01',      _tig_01(c).severity,      'pass'),       # 7000 > 6000 → pass
    ('TIG-20',      _tig_20(c).severity,      'pass'),
    ('TIG-20.1',    _tig_20_1(c).severity,    'pass'),
    ('WATCH-22.5',  _watch_22_5(c).severity,  'pass'),       # 2 creditors both ≥ £500 → pass
    ('WATCH-22.8',  _watch_22_8(c).severity,  'pass'),
    ('WATCH-22.10', _watch_22_10(c).severity, 'pass'),
    ('TIX-04',      _tix_04(c).severity,      'pass'),
    ('TIG-15.8',    _tig_15_8(c).severity,    'info'),
    ('TIG-15.9',    _tig_15_9(c).severity,    'info'),
]

print()
all_ok = True
for rule_id, got, expected in checks:
    ok = got == expected
    if not ok:
        all_ok = False
    status = 'OK  ' if ok else 'FAIL'
    print(f'  {status} {rule_id}: expected={expected}, got={got}')

print()
print('ALL CHECKS PASSED' if all_ok else 'FAILURES FOUND - SEE ABOVE')
