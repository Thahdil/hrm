#!/usr/bin/env python3
import os
import sys
import django

# Setup Django
os.chdir('src')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from core.models import AuditLog

# Create the table using Django's schema editor
with connection.schema_editor() as schema_editor:
    try:
        schema_editor.create_model(AuditLog)
        print("✓ Successfully created core_auditlog table")
    except Exception as e:
        print(f"Error creating table: {e}")
        print("Trying to check if table already exists...")
        
# Verify table was created
with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='core_auditlog'")
    result = cursor.fetchone()
    if result:
        print("✓ Table core_auditlog exists in database")
    else:
        print("✗ Table core_auditlog NOT found")
