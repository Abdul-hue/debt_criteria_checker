"""Run migration 0075's forward data step without applying 0073/0074.

0075 (reparent_group_caps_into_natural_categories) is a pure RunPython data
migration. Its only schema prerequisite is 0072, which is applied; Django's
dependency graph nevertheless refuses to reach it without first running the
0073/0074 guideline data sync. This script runs 0075's own forwards() against
the live app registry instead.

Leaving 0075 unrecorded in django_migrations is deliberate and self-correcting:
a later full `manage.py migrate` runs 0073 (which recreates the 'Group Caps'
category and reparents these three rows back into it), then 0074, then 0075
again - converging on exactly this state.

Idempotent: re-running when 'Group Caps' is already absent is a no-op.

    python scripts/dev/apply_0075_data_step.py
"""
import importlib.util
import os
import sys

import django

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from django.apps import apps as live_apps  # noqa: E402

MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "debt_app", "migrations",
    "0075_reparent_group_caps_into_natural_categories.py",
)

spec = importlib.util.spec_from_file_location("mig0075", os.path.abspath(MIGRATION))
mig = importlib.util.module_from_spec(spec)
sys.modules["mig0075"] = mig
spec.loader.exec_module(mig)

mig.forwards(live_apps, None)
print("0075 forward data step complete")
