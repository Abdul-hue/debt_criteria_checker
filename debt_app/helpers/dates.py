"""Timezone helpers (Europe/London day boundaries)."""

from django.utils import timezone

def get_london_day_boundary(dt=None):
    """
    Given a datetime (defaulting to now), return the Europe/London calendar-day
    boundaries as timezone-aware datetime instants (day_start, day_end) and
    the London date object itself.
    """
    from datetime import datetime, time, timedelta
    if dt is None:
        dt = timezone.now()
    london_date = timezone.localtime(dt).date()
    current_tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(london_date, time.min), current_tz)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end, london_date
