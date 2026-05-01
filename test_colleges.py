import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ams_project.settings')
django.setup()
from admission_system.models import College
for c in College.objects.all():
    if "Jai" in c.name or "Bharath" in c.name:
        print(f"Name: {c.name}, Slug: {c.slug}")
