import sys
import os
sys.path.append('src')

import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import AuditLog

def clear_logs():
    print(f"Current Audit Logs: {AuditLog.objects.count()}")
    print("Deleting all Audit Logs...")
    AuditLog.objects.all().delete()
    print("Deleted.")

    print("Vacuuming database...")
    with connection.cursor() as cursor:
        cursor.execute("VACUUM")
    
    db_size = os.path.getsize('src/db.sqlite3') / (1024*1024)
    print(f"New DB Size: {db_size:.2f} MB")

if __name__ == '__main__':
    clear_logs()
