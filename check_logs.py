#!/usr/bin/env python3
import os
import sys
import django

# Setup Django
os.chdir('src')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.admin.models import LogEntry

# Count total logs
total = LogEntry.objects.all().count()
print(f'Total Audit Logs: {total}')

if total > 0:
    print('\nRecent 10 logs:')
    for log in LogEntry.objects.select_related('user', 'content_type').order_by('-action_time')[:10]:
        action = {1: 'ADD', 2: 'CHANGE', 3: 'DELETE'}.get(log.action_flag, 'UNKNOWN')
        print(f'  [{log.action_time.strftime("%Y-%m-%d %H:%M")}] {log.user.username} - {action} - {log.object_repr}')
else:
    print('No audit logs found.')
