import datetime
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Min, Max
from django.utils import timezone
from debt_app.models import CreditorResolutionMiss

class Command(BaseCommand):
    help = 'Review creditors that failed to resolve (UNKNOWN status)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Limit to last N days (default 7)'
        )
        parser.add_argument(
            '--min-count',
            type=int,
            default=2,
            help='Only show names appearing N or more times (default 2)'
        )

    def handle(self, *args, **options):
        days = options['days']
        min_count = options['min_count']
        cutoff_date = timezone.now() - datetime.timedelta(days=days)

        # Query and aggregate
        misses = (
            CreditorResolutionMiss.objects.filter(
                resolved=False,
                logged_at__gte=cutoff_date
            )
            .values('raw_name')
            .annotate(
                count=Count('id'),
                total_balance=Sum('balance'),
                first_seen=Min('logged_at'),
                last_seen=Max('logged_at')
            )
            .filter(count__gte=min_count)
            .order_by('-count')
        )

        if not misses:
            self.stdout.write(self.style.SUCCESS(f"No unresolved misses found in the last {days} days with count >= {min_count}."))
            return

        # Header
        header = f"{'Rank':<4} | {'Raw Name':<80} | {'Count':<5} | {'Total Bal':<12} | {'First Seen':<10} | {'Last Seen':<10}"
        self.stdout.write(self.style.MIGRATE_HEADING(header))
        self.stdout.write("-" * len(header))

        for i, miss in enumerate(misses, 1):
            raw_name = miss['raw_name'][:80]
            count = miss['count']
            total_balance = float(miss['total_balance'] or 0)
            first_seen = miss['first_seen'].strftime('%Y-%m-%d')
            last_seen = miss['last_seen'].strftime('%Y-%m-%d')

            line = f"{i:<4} | {raw_name:<80} | {count:<5} | £{total_balance:>10.2f} | {first_seen:<10} | {last_seen:<10}"
            self.stdout.write(line)

        self.stdout.write(self.style.SUCCESS(f"\nFound {len(misses)} unique unresolved creditors."))
