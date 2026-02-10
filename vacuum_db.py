import sqlite3
import os

db_path = 'src/db.sqlite3'

def vacuum_database():
    try:
        # Get initial size
        initial_size = os.path.getsize(db_path) / (1024 * 1024)
        print(f"Initial DB Size: {initial_size:.2f} MB")

        # Connect and Vacuum
        conn = sqlite3.connect(db_path)
        print("Running VACUUM...")
        conn.execute("VACUUM")
        conn.close()

        # Get final size
        final_size = os.path.getsize(db_path) / (1024 * 1024)
        print(f"Final DB Size: {final_size:.2f} MB")
        
        if final_size < 100:
            print("SUCCESS: Database is now under 100MB and can be pushed to GitHub!")
        else:
            print("WARNING: Database is still over 100MB.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    vacuum_database()
