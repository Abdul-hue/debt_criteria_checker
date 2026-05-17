"""Migrate db_fresh.sqlite3 from zero (Phase 3.5)."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
FRESH_DB = BASE / "db_fresh.sqlite3"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")

import django

django.setup()

from django.conf import settings
from django.core.management import call_command

if FRESH_DB.exists():
    FRESH_DB.unlink()
    print(f"Removed existing {FRESH_DB}")

settings.DATABASES["default"]["NAME"] = FRESH_DB

print(f"Migrating fresh database: {FRESH_DB}")
call_command("migrate", verbosity=2, interactive=False)
print("Done.")
