import os
import django
import shutil

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from leaves.models import LeaveRequest, LeaveBalance
from employees.models import DocumentVault
from django.conf import settings

def clear_all_data():
    print("Clearing Leave Requests...")
    # 1. Clear Leave Requests
    LeaveRequest.objects.all().delete()
    print("✓ All Leave Requests deleted.")

    print("Clearing Leave Balances...")
    # 2. Clear Leave Balances (optional but good for clean slate)
    LeaveBalance.objects.all().delete() 
    print("✓ All Leave Balances deleted.")

    print("Clearing Document Vault...")
    # 3. Clear Document Vault (Database records)
    docs = DocumentVault.objects.all()
    # Delete physical files too?
    # The delete() method on model usually handles file deletion if configured, 
    # lets assume standard Django behavior or manual cleanup needed.
    # We will manually clean up the media/secure_docs folder to be safe.
    docs.delete()
    print("✓ All Document Vault records deleted.")
    
    # 4. Clear Uploaded Files in Media
    secure_docs_path = os.path.join(settings.MEDIA_ROOT, 'secure_docs')
    if os.path.exists(secure_docs_path):
        try:
            shutil.rmtree(secure_docs_path)
            os.makedirs(secure_docs_path) # Recreate empty folder
            print(f"✓ Cleared files in {secure_docs_path}")
        except Exception as e:
            print(f"Error clearing files: {e}")
    else:
        print(f"Directory {secure_docs_path} does not exist.")

if __name__ == '__main__':
    clear_all_data()
    print("\nDone! System is clean.")
