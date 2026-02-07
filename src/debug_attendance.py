import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payroll.models import AttendanceLog, RawPunch

# Look at AMOS
logs = AttendanceLog.objects.filter(
    employee__username__icontains='AMOS',
).order_by('-date')

# If still not found, get last 100
if not logs.exists():
    logs = AttendanceLog.objects.order_by('-id')[:100]

for log in logs:
    print(f"ID: {log.id} | User: {log.employee.username} | Date: {log.date} | Status: {log.status} | Holiday: {log.is_holiday} | Minutes: {log.total_work_minutes}")
    punches = log.raw_punches.all().order_by('time')
    sorted_punches = sorted([(p.time, p.punch_type.lower()) for p in punches], key=lambda x: (x[0], 0 if x[1] == 'in' else 1))
    for p in punches:
        print(f"  - {p.time} | {p.punch_type}")
    print(f"  - Sorted: {sorted_punches}")
    print(f"  - Cleaned: {log._get_cleaned_punches()}")
    print(f"  - Hours Str: {log.hours_str}")
    print("-" * 30)
