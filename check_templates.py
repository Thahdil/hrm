import os
import sys
import django
from django.conf import settings
from django.template import Template, TemplateSyntaxError

# Setup Django
sys.path.append(os.path.abspath('src'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def check_templates():
    template_dir = os.path.join('src', 'templates')
    has_errors = False
    
    for root, dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        Template(content)
                        # print(f"OK: {path}")
                except TemplateSyntaxError as e:
                    print(f"❌ SYNTAX ERROR in {path}:")
                    print(f"   {e}")
                    has_errors = True
                except Exception as e:
                    print(f"⚠️ ERROR in {path}: {e}")
                    has_errors = True
    
    if not has_errors:
        print("✅ No template syntax errors found in the entire project.")

if __name__ == '__main__':
    check_templates()
