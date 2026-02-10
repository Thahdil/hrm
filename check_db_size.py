import sys
import os
sys.path.append('src') # Correct path for Django apps

import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def check_table_sizes():
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        table_counts = []
        for table in tables:
            tname = table[0]
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tname}")
                count = cursor.fetchone()[0]
                table_counts.append((tname, count))
            except:
                pass
                
        table_counts.sort(key=lambda x: x[1], reverse=True)
        
        print(f"\n{'Table Name':<30} | {'Row Count'}")
        print("-" * 45)
        for name, count in table_counts[:15]:
            print(f"{name:<30} | {count}")

if __name__ == '__main__':
    check_table_sizes()
