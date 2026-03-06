import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute("PRAGMA journal_mode;")
    print("JM:", c.fetchone())
    c.execute("PRAGMA synchronous;")
    print("SYNC:", c.fetchone())
    c.execute("PRAGMA cache_size;")
    print("CACHE:", c.fetchone())
    c.execute("PRAGMA temp_store;")
    print("TEMP:", c.fetchone())
