#!/usr/bin/env python3
import os
import sys
import sqlite3

# Change to src directory
os.chdir('src')

db_path = 'db.sqlite3'

print(f"Working directory: {os.getcwd()}")
print(f"Database path: {os.path.abspath(db_path)}")
print(f"Database exists: {os.path.exists(db_path)}")

if not os.path.exists(db_path):
    print("ERROR: Database file not found!")
    sys.exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n1. Dropping existing table...")
    cursor.execute('DROP TABLE IF EXISTS core_auditlog')
    conn.commit()
    print("   ✓ Dropped")
    
    print("\n2. Creating core_auditlog table...")
    cursor.execute('''
    CREATE TABLE core_auditlog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action VARCHAR(20) NOT NULL,
        module VARCHAR(20) NOT NULL DEFAULT 'OTHER',
        object_id INTEGER,
        object_repr VARCHAR(200),
        changes TEXT,
        ip_address VARCHAR(39),
        user_agent TEXT,
        timestamp DATETIME NOT NULL,
        content_type_id INTEGER,
        user_id INTEGER
    )
    ''')
    conn.commit()
    print("   ✓ Table created")
    
    print("\n3. Creating indexes...")
    cursor.execute('CREATE INDEX core_auditl_timesta_idx ON core_auditlog (timestamp DESC)')
    cursor.execute('CREATE INDEX core_auditl_user_id_idx ON core_auditlog (user_id, timestamp DESC)')
    cursor.execute('CREATE INDEX core_auditl_action_idx ON core_auditlog (action, timestamp DESC)')
    cursor.execute('CREATE INDEX core_auditl_module_idx ON core_auditlog (module, timestamp DESC)')
    conn.commit()
    print("   ✓ Indexes created")
    
    print("\n4. Verifying table...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='core_auditlog'")
    result = cursor.fetchone()
    
    if result:
        print(f"   ✓ Table exists: {result[0]}")
        
        cursor.execute('PRAGMA table_info(core_auditlog)')
        columns = cursor.fetchall()
        print(f"\n5. Table structure ({len(columns)} columns):")
        for col in columns:
            print(f"   - {col[1]:20s} {col[2]}")
    else:
        print("   ✗ ERROR: Table not found after creation!")
        sys.exit(1)
    
    conn.close()
    print("\n✅ SUCCESS: core_auditlog table is ready!")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
