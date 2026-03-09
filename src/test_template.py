import os
import django
import sys

# Set up Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.template.loader import render_to_string
from users.models import CustomUser

# Get an admin user
admin_user = CustomUser.objects.filter(role='ADMIN').first()
if not admin_user:
    print("No admin user found.")
    sys.exit(1)

html = render_to_string('system_admin.html', {'user': admin_user})
if "Roles & Permissions" in html:
    print("SUCCESS: Found 'Roles & Permissions' in rendered system_admin.html.")
else:
    print("FAILURE: 'Roles & Permissions' is NOT in rendered system_admin.html.")
    
# Debug output to see what WAS in the HTML
print("\n--- Snippet of rendered HTML (Policy & Configuration) ---")
lines = html.split('\n')
start = -1
for i, line in enumerate(lines):
    if "Policy & Configuration" in line:
        start = i
        break
        
if start != -1:
    for i in range(start, min(start+30, len(lines))):
        print(lines[i])
