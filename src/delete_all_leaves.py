
import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from leaves.models import LeaveRequest

try:
    count = LeaveRequest.objects.count()
    print(f"Found {count} leave requests.")
    if count > 0:
        LeaveRequest.objects.all().delete()
        print(f"Successfully deleted {count} leave requesting records.")
    else:
        print("No leave requests found to delete.")
except Exception as e:
    print(f"Error occurred: {e}")
