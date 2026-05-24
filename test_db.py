import os
import django
from django.db import connections
from django.db.utils import OperationalError

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

def test_aryza_connection():
    print("Testing connection to 'aryza' database...")
    try:
        connection = connections['aryza']
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print(f"Connection successful! Result: {result}")
    except OperationalError as e:
        print(f"Connection failed: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_aryza_connection()
