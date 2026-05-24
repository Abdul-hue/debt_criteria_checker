import os
import django
import sys

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.aryza_client import (
    fetch_case_by_reference,
    AryzaCaseNotFoundError,
    AryzaConnectionError,
    AryaTimeoutError,
    AryzaDataError
)

def pence_to_pounds(pence):
    if pence is None:
        return "£0.00"
    return f"£{pence / 100:,.2f}"

def format_bool(val):
    return "Yes" if val else "No"

def format_value(val):
    if val is None:
        return "None"
    return str(val)

def main():
    case_ref = "324991"
    try:
        case = fetch_case_by_reference(case_ref)
        data = case.to_dict()
    except AryzaCaseNotFoundError:
        print(f"Case {case_ref} not found in Aryza")
        sys.exit(0)
    except AryzaConnectionError:
        print("Could not connect to Aryza database")
        sys.exit(0)
    except AryaTimeoutError:
        print("Aryza connection timed out")
        sys.exit(0)
    except AryzaDataError as e:
        print(str(e))
        sys.exit(0)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

    print("=" * 60)
    print(f"CASE: {data['aryza_reference']} — {data['client_name']}")
    print("=" * 60)
    print()

    print("--- IDENTIFIERS ---")
    print(f"Aryza Reference : {data['aryza_reference']}")
    print(f"Client ID       : {data['clientid']}")
    print(f"Client Name     : {data['client_name']}")
    print(f"Employment      : {data['employment_status']}")
    print()

    print("--- FINANCIALS ---")
    print(f"Total Unsecured Debt : {pence_to_pounds(data['total_unsecured_debt'])}")
    print(f"Disposable Income    : {pence_to_pounds(data['disposable_income'])}")
    print()

    income = data['income']
    print("--- INCOME (monthly) ---")
    print(f"Employment Income         : {pence_to_pounds(income.get('employment'))}")
    print(f"Universal Credit          : {pence_to_pounds(income.get('universal_credit'))}")
    print(f"DLA                       : {pence_to_pounds(income.get('dla'))}")
    print(f"PIP                       : {pence_to_pounds(income.get('pip'))}")
    print(f"Other Benefits            : {pence_to_pounds(income.get('other_benefits'))}")
    print(f"Third Party Contribution  : {pence_to_pounds(income.get('third_party_contribution'))}")
    print(f"Total Income              : {pence_to_pounds(income.get('total'))}")
    print()

    exp = data['expenditure']
    print("--- EXPENDITURE (monthly) ---")
    print(f"Disability Expenses : {pence_to_pounds(exp.get('disability_expenses'))}")
    print(f"Total Expenditure   : {pence_to_pounds(exp.get('total'))}")
    print()

    prop = data['property']
    print("--- PROPERTY ---")
    print(f"Owns Property    : {format_bool(prop.get('owns_property'))}")
    print(f"Property Value   : {pence_to_pounds(prop.get('property_value'))}")
    print(f"Mortgage Balance : {pence_to_pounds(prop.get('mortgage_balance'))}")
    print(f"Equity           : {pence_to_pounds(prop.get('equity'))}")
    print()

    veh = data['vehicle']
    print("--- VEHICLE ---")
    print(f"Has Vehicle          : {format_bool(veh.get('has_vehicle'))}")
    print(f"Vehicle Value        : {pence_to_pounds(veh.get('vehicle_value'))}")
    print(f"HP Monthly Payment   : {pence_to_pounds(veh.get('hp_monthly_payment'))}")
    print(f"Finance Start Date   : {format_value(veh.get('car_finance_start_date'))}")
    print()

    flags = data['flags']
    print("--- FLAGS ---")
    print(f"Previous IVA             : {format_bool(flags.get('previous_iva'))}")
    print(f"Previous IVA Fail Reason : {format_value(flags.get('previous_iva_failed_reason'))}")
    print(f"Gambling Present         : {format_bool(flags.get('gambling_present'))}")
    print(f"Antecedent Transactions  : {format_bool(flags.get('antecedent_transactions'))}")
    print(f"Vulnerability Claimed    : {format_bool(flags.get('vulnerability_claimed'))}")
    print(f"Has Third Party          : {format_bool(flags.get('has_third_party'))}")
    print()

    creditors = data.get('creditors', [])
    print(f"--- CREDITORS ({len(creditors)} found) ---")
    for i, creditor in enumerate(creditors, 1):
        print(f"  {i}. {creditor.get('name')}")
        print(f"      Balance      : {pence_to_pounds(creditor.get('balance'))}")
        print(f"      Type         : {format_value(creditor.get('type'))}")
        print(f"      Is HMRC      : {format_bool(creditor.get('is_hmrc'))}")
        print(f"      Is Council   : {format_bool(creditor.get('is_council'))}")
        print(f"      From Credit Report : {format_bool(creditor.get('is_credit_report'))}")
    print()

    deps = data.get('dependants', [])
    print(f"--- DEPENDANTS ({len(deps)} found) ---")
    for i, dep in enumerate(deps, 1):
        print(f"  {i}. Age: {dep.get('age')}")
    print()

    print("=" * 60)
    print("DIAGNOSIS")
    print("=" * 60)
    
    no_data = []
    has_data = []

    def check_field(label, value):
        if value in [0, 0.0, None, False, "", [], {}]:
            no_data.append(label)
        else:
            has_data.append(label)

    check_field("Client ID", data.get('clientid'))
    check_field("Client Name", data.get('client_name'))
    check_field("Employment Status", data.get('employment_status'))
    check_field("Total Unsecured Debt", data.get('total_unsecured_debt'))
    check_field("Disposable Income", data.get('disposable_income'))
    
    for k, v in income.items():
        check_field(f"Income: {k}", v)
    
    for k, v in exp.items():
        check_field(f"Expenditure: {k}", v)
        
    for k, v in prop.items():
        check_field(f"Property: {k}", v)
        
    for k, v in veh.items():
        check_field(f"Vehicle: {k}", v)
        
    for k, v in flags.items():
        check_field(f"Flag: {k}", v)
        
    check_field("Creditors List", creditors)
    check_field("Dependants List", deps)

    print("Fields with no data (zero / null / false / empty):")
    for field in no_data:
        print(f"  - {field}")
    print()

    print("Fields with data:")
    for field in has_data:
        print(f"  - {field}")
    print("=" * 60)

if __name__ == "__main__":
    main()
