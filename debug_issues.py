#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import (
    DepartmentFeaturePermission, Department, GlobalCriteria
)
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

# 1. Check permissions in database for Lead Generation
print("=" * 60)
print("1. CHECKING PERMISSIONS IN DATABASE")
print("=" * 60)
lg_dept = Department.objects.get(name='Lead Generation')
perms = DepartmentFeaturePermission.objects.filter(department=lg_dept).order_by('feature_key')
print(f"\nLead Generation has {perms.count()} permission records:")
for p in perms:
    print(f"  - {p.feature_key}: {p.permission_level}")

# 2. Test RulesDetailView.put() - simulate updating a rule
print("\n" + "=" * 60)
print("2. TESTING RULES UPDATE")
print("=" * 60)
rule = GlobalCriteria.objects.first()
if rule:
    original_active = rule.is_active
    rule.is_active = not original_active
    rule.save()
    rule.refresh_from_db()
    print(f"Rule {rule.rule_key}:")
    print(f"  Original is_active: {original_active}")
    print(f"  After save is_active: {rule.is_active}")
    print(f"  ✓ Update works correctly" if rule.is_active != original_active else "  ✗ Update FAILED")
else:
    print("No rules found")

# 3. Check if frontend is looking for permissions that don't have records
print("\n" + "=" * 60)
print("3. CHECKING PERMISSION RECORDS")
print("=" * 60)
expected_features = ['general_creditors', 'representative_creditors', 'global_rules', 'councils', 'dividends', 'sfs_guidelines']
print("\nExpected features and their permission records:")
for feature in expected_features:
    perm = DepartmentFeaturePermission.objects.filter(department=lg_dept, feature_key=feature).first()
    if perm:
        print(f"  ✓ {feature}: {perm.permission_level}")
    else:
        print(f"  ✗ {feature}: NO RECORD (will default to READ)")
