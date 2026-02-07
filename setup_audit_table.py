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
print("Creating AuditLog table...")
with connection.schema_editor() as schema_editor:
    try:
        # Drop if exists
        try:
            schema_editor.delete_model(AuditLog)
            print("✓ Dropped existing table")
        except:
            pass
        
        # Create new
        schema_editor.create_model(AuditLog)
        print("✓ Successfully created core_auditlog table with all fields")
    except Exception as e:
        print(f"Error: {e}")

# Verify table was created
with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='core_auditlog'")
    result = cursor.fetchone()
    if result:
        print("✓ Table core_auditlog exists in database")
        
        # Show columns
        cursor.execute("PRAGMA table_info(core_auditlog)")
        columns = cursor.fetchall()
        print("\nTable columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
    else:
        print("✗ Table core_auditlog NOT found")
