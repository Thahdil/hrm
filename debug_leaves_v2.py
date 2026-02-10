import os
import django
import sys
from django.db.models import Sum

# Setup Django environment
sys.path.append(os.path.join(os.getcwd(), 'src'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from leaves.models import LeaveRequest, LeaveBalance, LeaveType

User = get_user_model()
try:
    user = User.objects.filter(username__icontains='sreerag').first() or User.objects.first()
    print(f"User: {user.username} (ID: {user.id})")
    
    print("\n--- ALL LEAVE REQUESTS ---")
    reqs = LeaveRequest.objects.filter(employee=user).order_by('start_date')
    for r in reqs:
        print(f"ID: {r.id} | Type: {r.leave_type.name} | Status: {r.status} | Dates: {r.start_date} to {r.end_date} | Dur: {r.duration_days}")

    print("\n--- LEAVE BALANCES ---")
    balances = LeaveBalance.objects.filter(employee=user)
    for b in balances:
        print(f"Type: {b.leave_type.name} (Ent: {b.leave_type.days_entitlement}, Freq: {b.leave_type.accrual_frequency}, RM: {b.leave_type.reset_monthly}) | Total: {b.total_entitlement} | Used: {b.days_used} | Remaining: {b.remaining}")

except Exception as e:
    print(e)
