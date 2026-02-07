import os
import sys
import django
from django.core.management import call_command

# Absolute path to src
SRC_DIR = os.path.join(os.getcwd(), 'src')
sys.path.append(SRC_DIR)

# Correct settings module from manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Ensure migrations dir exists
mig_dir = os.path.join(SRC_DIR, 'payroll', 'migrations')
if not os.path.exists(mig_dir):
    os.makedirs(mig_dir)
    with open(os.path.join(mig_dir, '__init__.py'), 'w') as f: pass

with open('mig_output.txt', 'w') as f:
    try:
        f.write("Running makemigrations...\n")
        call_command('makemigrations', 'payroll', stdout=f, stderr=f)
        f.write("\nRunning migrate...\n")
        call_command('migrate', 'payroll', stdout=f, stderr=f)
        f.write("\nDone.")
    except Exception as e:
        import traceback
        f.write(f"\nERROR: {e}\n")
        traceback.print_exc(file=f)
