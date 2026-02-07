import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payroll.models import AttendanceLog

logs = AttendanceLog.objects.filter(total_work_minutes=1050)
print(f"Found {logs.count()} records with 1050 minutes.")
count = 0
for log in logs:
    old_mins = log.total_work_minutes
    new_mins = log.recalculate_duration()
    if old_mins != new_mins:
        count += 1
        print(f"Changed record {log.id} for {log.employee.username}: {old_mins} -> {new_mins}")

print(f"Fixed {count} records.")
