import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from leaves.models import LeaveRequest
from core.models import User
from decimal import Decimal
import datetime

u = User.objects.filter(username__icontains='anush').first()
if getattr(u, 'username', '') != '':
    print("User found", u.username)
    reqs = LeaveRequest.objects.filter(employee=u)
    for r in reqs:
        print(f"Leave: start {r.start_date} end {r.end_date} half_day {r.half_day} status {r.status} type {r.leave_type.name} is_paid {r.leave_type.is_paid} pay_stat {r.payment_status} sick {r.is_sick_leave}")
