import os
import sys
import django
from django.urls import resolve, Resolver404

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

def test_resolve():
    path = "/api/v1/criteria/assess/"
    print(f"Testing resolution of: {path}")
    try:
        match = resolve(path)
        print(f"  FOUND: {match.func}")
        print(f"  URL Name: {match.url_name}")
        print(f"  App Names: {match.app_names}")
    except Resolver404:
        print("  FAILED to resolve (404)")

if __name__ == "__main__":
    test_resolve()
