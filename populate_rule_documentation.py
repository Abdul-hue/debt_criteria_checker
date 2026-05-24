#!/usr/bin/env python
"""
Data Population Script: Load Rule Documentation from Markdown Files

This script extracts documentation from markdown criteria files and updates
the GlobalCriteria models with descriptions, examples, and metadata.
"""

import os
import django
import re
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import GlobalCriteria
from django.contrib.auth.models import User

# -----------------------------------------------------------------------------
# Data Mappings: Rule Key -> Documentation
# -----------------------------------------------------------------------------

RULE_DOCUMENTATION = {
    # TIG Rules
    'TIG-01': {
        'category': 'core_requirements',
        'description': 'Total unsecured debt must be at least £6,000.',
        'example_case': 'Client has debts totalling £5,500. Case REJECTED.',
        'rejection_message': 'Debt level below £6,000 threshold',
    },
    'TIG-02': {
        'category': 'core_requirements',
        'description': 'Client must have minimum disposable income of £100 per month after SFS expenditure.',
        'example_case': 'Client has DI of £90/month. Case REJECTED.',
        'rejection_message': 'Insufficient disposable income (minimum £100 required)',
    },
    'TIG-03': {
        'category': 'core_requirements',
        'description': 'Expenditure must align with Standard Financial Statement guidelines.',
        'flag_message': 'Expenditure categories exceed SFS guideline limits',
    },
    'TIG-04': {
        'category': 'core_requirements',
        'description': 'DLA/PIP receipts must be offset against disability-related expenditure before calculating disposable income.',
        'flag_message': 'DLA/PIP income present without offsetting disability expenditure',
    },
    'TIG-05': {
        'category': 'income',
        'description': 'Employed clients must provide recent wage slips (1 full month dated within the last 3 months).',
        'rejection_message': 'Wage slips must be dated within the last 3 months',
    },
    'TIG-06': {
        'category': 'income',
        'description': 'Benefit letters must be from current financial year or shown on recent bank statement.',
        'rejection_message': 'Benefit letters must be current or verified on bank statement',
    },
    'TIG-07': {
        'category': 'income',
        'description': 'Universal Credit: full journal dated in last 3 months required.',
        'rejection_message': 'Universal Credit journal must be dated within the last 3 months',
    },
    'TIG-08': {
        'category': 'income',
        'description': 'Self-employed clients require Tax Return or 3 months of bank statements.',
        'rejection_message': 'Self-employed clients require Tax Return or 3 months of bank statements',
    },
    'TIG-09': {
        'category': 'income',
        'description': 'CIS workers require minimum 1 month invoice showing 20% deduction.',
        'rejection_message': 'CIS workers require invoice showing 20% deduction',
    },
    'TIG-10': {
        'category': 'proof_of_debts',
        'description': 'Require proof of all debts to verify cases.',
        'rejection_message': 'Missing proof of debts (all debts over £1,000 require written evidence)',
    },
    'TIG-11': {
        'category': 'bank_statements',
        'description': 'Bank statements must be dated within last 3 months, 1 full month per account.',
        'rejection_message': 'Bank statements must be dated within the last 3 months',
    },
    'TIG-11-GAMBLING': {
        'category': 'bank_statements',
        'description': 'Gambling spending must be under £1,000; GAMSTOP required if over £200.',
        'rejection_message': 'Gambling spending exceeds £1,000 threshold',
        'flag_message': 'Gambling spend over £200 requires GAMSTOP evidence',
    },
    'TIG-12': {
        'category': 'proof_of_debts',
        'description': 'Third-party contribution evidence requires signed letter including duration.',
        'rejection_message': 'Third-party letters must be signed with contact information and state duration',
    },
    'TIG-13': {
        'category': 'proof_of_debts',
        'description': 'If the client has a previously terminated IVA, the termination report must be obtained.',
        'rejection_message': 'Previous IVA on record but no termination report uploaded',
    },
    'TIG-14': {
        'category': 'proof_of_debts',
        'description': 'Debts under £1,000 can be verbal if written proof unavailable.',
        'example_case': 'Client has £800 telephone debt, verbal confirmation acceptable.',
    },
    'TIG-15': {
        'category': 'proof_of_debts',
        'description': 'Creditor letters required within last 6 weeks with reference numbers.',
        'rejection_message': 'Creditor letters must be dated within the last 6 weeks',
    },
    'TIG-15.1': {
        'category': 'hmrc',
        'description': 'HMRC MUST NOT have a deduction from income or benefits.',
        'rejection_message': 'HMRC deduction from income or benefits present',
    },
    'TIG-15.2': {
        'category': 'hmrc',
        'description': 'HMRC WILL REJECT if previous IVA or Bankruptcy.',
        'rejection_message': 'HMRC reject due to previous IVA or Bankruptcy',
    },
    'TIG-15.3': {
        'category': 'hmrc',
        'description': 'HMRC Self Assessment: if still self-employed, will vote to reject if any late submissions.',
        'rejection_message': 'HMRC reject due to late Self Assessment submissions',
    },
    'TIG-15.4': {
        'category': 'hmrc',
        'description': 'HMRC Equity: WILL REJECT if more equity than their debt.',
        'rejection_message': 'HMRC reject due to equity exceeding debt',
    },
    'TIG-15.5': {
        'category': 'hmrc',
        'description': 'HMRC Bankruptcy Return: WILL REJECT if return higher in bankruptcy.',
        'rejection_message': 'HMRC reject due to higher return in bankruptcy',
    },
    'TIG-15.6': {
        'category': 'hmrc',
        'description': 'HMRC Full & Final: Wont accept full and final from savings if client avoiding paying debts.',
        'rejection_message': 'HMRC reject full and final from savings',
    },
    'TIG-15.7': {
        'category': 'hmrc',
        'description': 'SEISS Fraud: Recovery of incorrectly claimed SEISS CANNOT BE INCLUDED — FRAUD.',
        'rejection_message': 'SEISS Fraud debt cannot be included',
    },
    'TIG-15.8': {
        'category': 'hmrc',
        'description': 'HMRC Joint Debts: where a debt is joint, HMRC will chase the second party.',
        'flag_message': 'HMRC Joint Debt - second party will be chased',
    },
    'TIG-15.9': {
        'category': 'hmrc',
        'description': 'HMRC Minimum Debt Threshold: WILL NOT VOTE on debts lower than £4,000 unless rejecting.',
        'flag_message': 'HMRC debt under £4,000 - will not vote',
    },
    'TIG-15.10': {
        'category': 'hmrc',
        'description': 'HMRC Benefits Only: WILL REJECT if benefits only.',
        'rejection_message': 'HMRC reject due to benefits only income',
    },
    'TIG-HMRC-VOTE-NOT-GUARANTEED': {
        'category': 'hmrc',
        'description': 'Advisory flag — HMRC agreement to the IVA cannot be assumed.',
        'flag_message': 'HMRC is a creditor — specific confirmation required',
    },
    'TIG-HMRC-VAT-TRADING': {
        'category': 'hmrc',
        'description': 'VAT arrears present and client is still trading without a payment arrangement.',
        'rejection_message': 'VAT arrears and trading without arrangement',
    },
    'TIG-HMRC-PAYE-OBLIGATIONS': {
        'category': 'hmrc',
        'description': 'PAYE arrears — employer PAYE obligations must be current.',
        'rejection_message': 'PAYE obligations are not current',
    },
    'TIG-HMRC-TAX-CREDITS': {
        'category': 'hmrc',
        'description': 'Tax credit overpayment debt — treated as priority; confirm DWP deductions.',
        'flag_message': 'Tax credit overpayment debt present',
    },
    'TIG-HMRC-NI-CLASS': {
        'category': 'hmrc',
        'description': 'National Insurance debt — confirm Class 2/4 treatment.',
        'flag_message': 'National Insurance debt present',
    },
    'TIG-HMRC-ONGOING-TRADING': {
        'category': 'hmrc',
        'description': 'Client is currently trading with HMRC debt — specific written confirmation required.',
        'flag_message': 'Currently trading with HMRC debt',
    },
    'TIG-HMRC-ANTECEDENT': {
        'category': 'hmrc',
        'description': 'Antecedent/preferential payment to HMRC — hard block.',
        'rejection_message': 'Preferential/antecedent payment to HMRC detected',
    },
    'TIG-16': {
        'category': 'flags',
        'description': 'If total property equity exceeds total unsecured liabilities, an IVA may not be appropriate.',
        'flag_message': 'Equity exceeds liabilities - greater return in Bankruptcy',
    },
    'TIG-17': {
        'category': 'flags',
        'description': 'Where a council creditor holds the majority vote and has an active attachment of earnings.',
        'flag_message': 'Council Majority - active deduction check required',
    },
    'TIG-18': {
        'category': 'flags',
        'description': 'Significant spending in the 3 months prior to the IVA application must be reviewed.',
        'flag_message': 'Recent Spend equivalent to monthly salary in last 2 months',
    },
    'TIG-19': {
        'category': 'creditor_specific',
        'description': 'Shop Direct spending verification - credit report with granular details required',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Shop Direct', 'Very', 'Littlewoods'],
    },
    'TIG-19.1': {
        'category': 'creditor_specific',
        'description': 'Shop Direct recent spending within 3-4 months triggers hard block',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Shop Direct', 'Very', 'Littlewoods'],
        'rejection_message': 'Recent spending detected on Shop Direct account',
    },
    'TIG-SHOP-DIRECT-4MO-REVIEW': {
        'category': 'creditor_specific',
        'description': 'Shop Direct recent spending review flag',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Shop Direct', 'Very', 'Littlewoods'],
        'flag_message': 'Recent spending in 3-4 months on Shop Direct account',
    },
    'TIG-20': {
        'category': 'creditor_specific',
        'description': 'Creation/Sygma/Laser account spending verification',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Creation', 'Sygma', 'Laser'],
    },
    'TIG-20.1': {
        'category': 'creditor_specific',
        'description': 'Creation/Sygma/Laser recent spending within 3-4 months triggers hard block',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Creation', 'Sygma', 'Laser'],
        'rejection_message': 'Recent spending detected on Creation/Sygma/Laser account',
    },
    'TIG-21.1': {
        'category': 'creditor_specific',
        'description': 'Link Financial Mid SFS guidelines ONLY must be used.',
        'is_creditor_specific': True,
    },
    'TIG-21.2': {
        'category': 'creditor_specific',
        'description': 'Link Financial £12,000 minimum debt level.',
        'is_creditor_specific': True,
    },
    'TIG-21.3': {
        'category': 'creditor_specific',
        'description': 'Link Financial REJECT if equity is more than their debt.',
        'is_creditor_specific': True,
    },
    'TIG-21.4': {
        'category': 'creditor_specific',
        'description': 'Link Financial REJECT if benefits are more than 10% of household income.',
        'is_creditor_specific': True,
    },
    'TIG-21.5': {
        'category': 'creditor_specific',
        'description': 'Link Financial REJECT if previous IVA failed due to arrears.',
        'is_creditor_specific': True,
    },

    # WATCH Rules
    'WATCH-22.1': {
        'category': 'vulnerability',
        'description': 'WATCH creditors require evidence of any client vulnerability to be noted in the proposal.',
        'flag_message': 'Vulnerability evidence required for WATCH creditors',
    },
    'WATCH-22.2': {
        'category': 'rejection_criteria',
        'description': 'Debt can be paid off in less than 6 years.',
        'rejection_message': 'Debt repayable in under 6 years',
    },
    'WATCH-22.3': {
        'category': 'rejection_criteria',
        'description': 'Bankruptcy dividend is higher than IVA return.',
        'rejection_message': 'Bankruptcy dividend exceeds IVA return',
    },
    'WATCH-22.4': {
        'category': 'rejection_criteria',
        'description': 'Equity is greater than debt.',
        'rejection_message': 'Property equity exceeds total unsecured debt',
    },
    'WATCH-22.5': {
        'category': 'rejection_criteria',
        'description': 'Client only has debt with 1 lender. Need separate lender account of more than £500.',
        'rejection_message': 'Single creditor dominates without sufficient secondary debts',
    },
    'WATCH-22.6': {
        'category': 'rejection_criteria',
        'description': 'Any spending within 3 months (on all accounts).',
        'rejection_message': 'Recent spending detected in the last 3 months',
    },
    'WATCH-22.7': {
        'category': 'flags',
        'description': 'Client has children over 13 and no sustainability paragraph.',
        'flag_message': 'Children over 13 present - sustainability paragraph required',
    },
    'WATCH-22.8': {
        'category': 'flags',
        'description': 'Client aged 80 or above. Creditor will abstain from voting.',
        'flag_message': 'Client over 80 - WATCH will abstain',
    },
    'WATCH-22.9': {
        'category': 'assets',
        'description': 'Car value is more than £9,000 and funds brought into IVA. Request downgrade to £4,500.',
        'flag_message': 'Vehicle value exceeds £9,000 threshold',
    },
    'WATCH-22.10': {
        'category': 'assets',
        'description': 'Car HP is > £400 per month (unless family help or valid reason evidenced).',
        'flag_message': 'Vehicle HP payment exceeds £400 per month',
    },
    'WATCH-22.11': {
        'category': 'flags',
        'description': 'Gambling as main cause of debt: Will require 3 months clean bank statement.',
        'flag_message': 'Gambling identified as main cause - 3 months clean statements needed',
    },
    'WATCH-22.12': {
        'category': 'flags',
        'description': 'Previously proposed IVA: The main content needs to remain the same, or a reason must be provided for the changes.',
        'flag_message': 'Previously proposed IVA noted - review changes',
    },
    'WATCH-22.13': {
        'category': 'rejection_criteria',
        'description': 'Antecedent transactions appear — irrelevant of the dividend factor.',
        'rejection_message': 'Antecedent transactions identified',
    },
    'WATCH-22.14': {
        'category': 'rejection_criteria',
        'description': 'Car finance taken in last 3 months, without evidence of valid reason.',
        'rejection_message': 'Recent car finance taken in last 3 months',
    },

    # TIX Rules
    'TIX-01': {
        'category': 'creditor_specific',
        'description': 'Shop Direct (Very, Littlewoods) — spend in last 3 months.',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Shop Direct', 'Very', 'Littlewoods'],
        'rejection_message': 'Shop Direct recent spending detected',
    },
    'TIX-02': {
        'category': 'creditor_specific',
        'description': 'Shop Direct (Very, Littlewoods) — account is less than 6 months old (regardless of spend).',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Shop Direct', 'Very', 'Littlewoods'],
        'rejection_message': 'Shop Direct account under 6 months old',
    },
    'TIX-03': {
        'category': 'creditor_specific',
        'description': 'Creation (Sygma, Laser) — spend in last 4 months.',
        'is_creditor_specific': True,
        'applies_to_creditors': ['Creation', 'Sygma', 'Laser'],
        'rejection_message': 'Creation/Sygma/Laser recent spending detected',
    },
    'TIX-04': {
        'category': 'assets',
        'description': 'Car HP is > £250 per month (unless family help or valid reason evidenced).',
        'flag_message': 'Vehicle HP payment exceeds £250 per month',
    },
    'TIX-05': {
        'category': 'flags',
        'description': 'TIX Ltd will no longer be representing UKAR, Whistletree, Computershare and Landmark.',
        'flag_message': 'Deregistered TIX creditor entity identified',
    },
    'TIX-06': {
        'category': 'vulnerability',
        'description': 'Will want evidence of any vulnerabilities being used to be outside of the standard criteria.',
        'flag_message': 'Vulnerability evidence required for TIX creditors',
    },

    # EVOLVE Rules
    'EVOLVE-01': {
        'category': 'rejection_criteria',
        'description': 'Equity is higher than debt level based on 100% LTV (85% LTV until further notice).',
        'rejection_message': 'Property equity exceeds debt level',
    },
    'EVOLVE-02': {
        'category': 'rejection_criteria',
        'description': 'Client only has debt with 1 lender — need separate lender account of more than £500.',
        'rejection_message': 'Single creditor dominates without sufficient secondary debts',
    },
    'EVOLVE-03': {
        'category': 'vulnerability',
        'description': 'Will want evidence of any vulnerabilities being used to be outside of the standard criteria.',
        'flag_message': 'Vulnerability evidence required for EVOLVE creditors',
    },
}

# Related Rules Mappings
RELATED_RULES_MAP = {
    'TIG-19': ['TIG-19.1'],
    'TIG-19.1': ['TIG-19'],
    'TIG-20': ['TIG-20.1'],
    'TIG-20.1': ['TIG-20'],
    'TIG-04': ['TIG-13'],
    'TIG-06': ['TIG-12'],
}


def populate_rule_documentation():
    """Populate rules with documentation from markdown"""
    print("\n" + "="*80)
    print("PHASE 4: Data Population - Rule Documentation")
    print("="*80)
    
    updated_count = 0
    skipped_count = 0
    
    # Get admin user for audit trail
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        print("⚠ No admin user found. Using None for audit trail.")
    
    for rule_key, doc_data in RULE_DOCUMENTATION.items():
        try:
            rule = GlobalCriteria.objects.get(rule_key=rule_key)
            
            # Update fields from documentation
            updated_fields = []
            
            if 'description' in doc_data and doc_data['description']:
                rule.description = doc_data['description']
                updated_fields.append('description')
            
            if 'category' in doc_data and doc_data['category']:
                rule.category = doc_data['category']
                updated_fields.append('category')
            
            if 'example_case' in doc_data and doc_data['example_case']:
                rule.example_case = doc_data['example_case']
                updated_fields.append('example_case')
            
            if 'rejection_message' in doc_data and doc_data['rejection_message']:
                rule.rejection_message = doc_data['rejection_message']
                updated_fields.append('rejection_message')
            
            if 'flag_message' in doc_data and doc_data['flag_message']:
                rule.flag_message = doc_data['flag_message']
                updated_fields.append('flag_message')
            
            if 'implementation_notes' in doc_data and doc_data['implementation_notes']:
                rule.implementation_notes = doc_data['implementation_notes']
                updated_fields.append('implementation_notes')
            
            if 'is_creditor_specific' in doc_data:
                rule.is_creditor_specific = doc_data['is_creditor_specific']
                updated_fields.append('is_creditor_specific')
            
            if 'applies_to_creditors' in doc_data and doc_data['applies_to_creditors']:
                rule.applies_to_creditors = doc_data['applies_to_creditors']
                updated_fields.append('applies_to_creditors')
            
            # Set related rules
            if rule_key in RELATED_RULES_MAP:
                rule.related_rules = RELATED_RULES_MAP[rule_key]
                updated_fields.append('related_rules')
            
            # Set last reviewed and review notes
            rule.last_reviewed = date.today()
            rule.review_notes = 'Auto-populated from markdown documentation during Phase 4'
            rule.updated_by = admin
            updated_fields.extend(['last_reviewed', 'review_notes'])
            
            rule.save()
            
            status_str = '[UPDATED]' if updated_fields else '[SKIPPED]'
            fields_str = ', '.join(updated_fields[:3]) + ('...' if len(updated_fields) > 3 else '')
            print(f"  {status_str} {rule_key:30} | Updated: {fields_str}")
            updated_count += 1
            
        except GlobalCriteria.DoesNotExist:
            print(f"  [NOT FOUND] {rule_key:30} | NOT FOUND in database")
            skipped_count += 1
    
    # Print summary
    print("\n" + "-"*80)
    print(f"Summary:")
    print(f"  [OK] Updated:  {updated_count} rules")
    print(f"  [SKIP] Skipped:  {skipped_count} rules (not in database)")
    print("-"*80 + "\n")
    
    return updated_count, skipped_count


if __name__ == '__main__':
    populate_rule_documentation()
