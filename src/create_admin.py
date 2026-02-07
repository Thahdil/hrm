import os
import sys
import django

# Add the project directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model

try:
    User = get_user_model()
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin')
        print('Superuser "admin" created with password "admin".')
    else:
        print('Superuser "admin" already exists.')
except Exception as e:
    print(f"Error creating superuser: {e}")
