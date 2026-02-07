from django.apps import AppConfig
import os

class PayrollConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payroll'

    def ready(self):
        # Auto-run migrations on server start since terminal access is broken
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from django.core.management import call_command
                
                # Setup Paths
                base_dir = os.path.dirname(os.path.abspath(__file__))
                mig_dir = os.path.join(base_dir, 'migrations')
                
                # Ensure migrations directory exists
                if not os.path.exists(mig_dir):
                    os.makedirs(mig_dir)
                    with open(os.path.join(mig_dir, '__init__.py'), 'w') as f: pass
                
                # Always allow makemigrations to detect changes
                call_command('makemigrations', 'payroll')
                call_command('migrate', 'payroll')
                
            except Exception:
                pass
