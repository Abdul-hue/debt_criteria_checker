import pytest
import json
import os

@pytest.fixture
def case_payloads():
    """
    Load the three real case payloads from JSON files.
    Files are expected to be in the project root.
    """
    payloads = {}
    case_ids = ['324991', '332591', '349223']
    
    for case_id in case_ids:
        file_path = f"payload_{case_id}.json"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-16') as f:
                payloads[case_id] = json.load(f)
        else:
            # Fallback for different environments if needed
            pass
            
    return payloads

@pytest.fixture
def theresa_topp_payload(case_payloads):
    return case_payloads.get('324991')

@pytest.fixture
def cristian_iancu_payload(case_payloads):
    return case_payloads.get('332591')

@pytest.fixture
def daniel_gallagher_payload(case_payloads):
    return case_payloads.get('349223')
