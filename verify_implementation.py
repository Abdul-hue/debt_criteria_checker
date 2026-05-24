#!/usr/bin/env python
"""
Verification script for creditor resolution implementation.
Tests the API with case 324991 and verifies the response structure.
"""

import os
import sys
import django
import json
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from django.test import Client

def test_creditor_resolution():
    """Test creditor resolution with case 324991"""
    
    # Create test user
    user, _ = User.objects.get_or_create(
        username='test_verify',
        defaults={'is_staff': True, 'is_superuser': True}
    )
    
    # Generate token
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    
    # Create client and make request
    client = Client()
    
    print("=" * 70)
    print("CREDITOR RESOLUTION VERIFICATION TEST")
    print("=" * 70)
    print()
    
    response = client.post(
        '/api/v1/criteria/assess/',
        data=json.dumps({'aryza_reference': '324991'}),
        content_type='application/json',
        HTTP_AUTHORIZATION=f'Bearer {access_token}'
    )
    
    print(f"Response Status: {response.status_code}")
    print()
    
    if response.status_code == 200:
        data = json.loads(response.content)
        
        # Check response structure
        print("Response keys present:")
        required_keys = [
            'success', 'decision_id', 'client_name', 'aryza_reference',
            'evaluated_at', 'disposable_income', 'total_unsecured_debt',
            'creditor_positions', 'overall_status'
        ]
        for key in required_keys:
            if key in data:
                print(f"  OK: {key}")
            else:
                print(f"  MISSING: {key}")
        
        print()
        print(f"Creditor Positions: {len(data.get('creditor_positions', []))} creditors")
        print()
        print("Creditors:")
        for c in data.get('creditor_positions', []):
            print(f"  * {c['creditor_name']}: {c['effective_status']} (GBP{c['balance']:.2f})")
        
        # Verify specific creditors
        print()
        print("Expected Creditors Verification:")
        expected = [
            ('PRA Group', 'ACCEPT'),  # Resolved from 'Natwest Group Plc'
            ('Lloyds Bank', 'ACCEPT'),  # Multiple occurrences grouped
            ('MBNA', 'ACCEPT'),  # Direct match
            ('Link Financial - IVA', 'ACCEPT'),  # Resolved from 'Link Financial Outsourcing Limited'
            ('Shop Direct', 'ACCEPT'),  # Resolved from 'JD Williams (N Brown Group)'
        ]
        
        position_names = {c['creditor_name']: c['effective_status'] 
                         for c in data.get('creditor_positions', [])}
        
        for name, expected_status in expected:
            if name in position_names:
                actual_status = position_names[name]
                if actual_status == expected_status:
                    print(f"  OK: {name}: {actual_status}")
                else:
                    print(f"  WARNING: {name}: expected {expected_status}, got {actual_status}")
            else:
                print(f"  MISSING: {name}: NOT FOUND")
        
    else:
        print(f"Error: {response.content.decode()}")
    
    print()
    print("=" * 70)

if __name__ == '__main__':
    test_creditor_resolution()
