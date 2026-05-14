from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = 'Discover Aryza database tables and column schema from the aryza database connection.'

    KEYWORDS = [
        'client',
        'case',
        'debt',
        'creditor',
        'income',
        'expense',
        'application',
    ]

    def handle(self, *args, **options):
        try:
            with connections['aryza'].cursor() as cursor:
                cursor.execute('SHOW TABLES')
                tables = [row[0] for row in cursor.fetchall()]
        except OperationalError as exc:
            self.stderr.write('ERROR: Unable to connect to the aryza database:')
            self.stderr.write(str(exc))
            return

        self.stdout.write(self.style.SUCCESS(f'Found {len(tables)} tables in Aryza database.'))
        self.stdout.write('')

        for table in tables:
            self.stdout.write(f'Table: {table}')
            if any(keyword in table.lower() for keyword in self.KEYWORDS):
                self.stdout.write('  Columns:')
                try:
                    with connections['aryza'].cursor() as cursor:
                        safe_table = table.replace('`', '``')
                        cursor.execute(f'SHOW COLUMNS FROM `{safe_table}`')
                        columns = cursor.fetchall()
                except OperationalError as exc:
                    self.stderr.write(f'ERROR: Unable to inspect columns for table {table}:')
                    self.stderr.write(str(exc))
                    continue

                for column in columns:
                    column_name = column[0]
                    column_type = column[1]
                    is_nullable = column[2]
                    key = column[3]
                    default = column[4]
                    extra = column[5]
                    self.stdout.write(
                        f'    - {column_name} | {column_type} | NULL={is_nullable} | KEY={key} | DEFAULT={default} | EXTRA={extra}'
                    )
            self.stdout.write('')
