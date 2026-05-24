import os
import django
import json
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.aryza_client import AryzaClient

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

import sys

client = AryzaClient()
ref = sys.argv[1] if len(sys.argv) > 1 else '324991'
case_data_obj = client.fetch_case_by_reference(ref)
raw_dict = case_data_obj.to_dict()

print(json.dumps(raw_dict, indent=2, default=decimal_default))
