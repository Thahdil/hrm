import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

sreerag = User.objects.filter(full_name__icontains='Sreerag').first()
if not sreerag:
    sreerag = User.objects.filter(username__icontains='Sreerag').first()

if sreerag:
    print(f"User Found: {sreerag.username} | Full Name: {sreerag.full_name} | Emp ID: {sreerag.employee_id} | Aadhaar: {sreerag.aadhaar_number}")
else:
    print("User Sreerag NOT found in DB")

# Also list all users to see if there's a naming mismatch
print("\nAll Users:")
for u in User.objects.all():
    print(f"- {u.username} | {u.full_name} | {u.employee_id}")
