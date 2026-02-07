#!/usr/bin/env python3
import os
import sys
import django

# Setup Django
os.chdir('src')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import AuditLog
from django.contrib.auth import get_user_model

User = get_user_model()

# Create sample audit logs
admin_user = User.objects.filter(role='ADMIN').first()
if not admin_user:
    admin_user = User.objects.first()

if admin_user:
    # Sample login log
    AuditLog.log(
        user=admin_user,
        action='LOGIN',
        obj=None,
        changes=None,
        request=None
    )
    print(f"✓ Created LOGIN log for {admin_user.username}")
    
    # Sample create log
    from core.models import CompanySettings
    company = CompanySettings.load()
    AuditLog.log(
        user=admin_user,
        action='UPDATE',
        obj=company,
        changes={'name': {'old': 'Old Name', 'new': company.name}},
        request=None
    )
    print(f"✓ Created UPDATE log for Company Settings")
    
    print(f"\nTotal audit logs: {AuditLog.objects.count()}")
    print("\nRecent logs:")
    for log in AuditLog.objects.order_by('-timestamp')[:5]:
        print(f"  - [{log.timestamp}] {log.user.username} {log.action} {log.object_repr}")
else:
    print("No users found in database")
