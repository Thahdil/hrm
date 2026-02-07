
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from leaves.models import LeaveType

types = LeaveType.objects.all()
print(f"{'Name':<20} | {'Code':<10} | {'Duration (Days)':<15}")
print("-" * 50)
for t in types:
    print(f"{t.name:<20} | {t.code:<10} | {t.duration_days}")
