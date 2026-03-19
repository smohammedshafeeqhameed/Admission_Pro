import os
import django
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ams_project.settings')
django.setup()

from admission_system.models import College, Course
from django.contrib.auth.models import User

def seed_data():
    # Create Superuser if not exists
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        print("Superuser created: admin / admin123")

    # Create some Colleges and Courses
    colleges_data = [
        {
            "name": "St. Andrews Engineering College",
            "slug": "st-andrews",
            "description": "A premier institute for engineering and technology.",
            "content": "<h3>Why choose us?</h3><ul><li>State-of-the-art labs</li><li>Industry placements</li><li>Modern campus</li></ul>",
            "courses": ["Computer Science", "Mechanical Engineering", "Civil Engineering"]
        },
        {
            "name": "Global Medical Institute",
            "slug": "global-medical",
            "description": "Excellence in medical education and research.",
            "content": "<h3>Our Facilities</h3><p>Affiliated with top hospitals. Focus on practical clinical experience.</p>",
            "courses": ["MBBS", "BDS", "Nursing"]
        },
        {
            "name": "Horizon Business School",
            "slug": "horizon-business",
            "description": "Leading the way in management and entrepreneurship.",
            "content": "<h3>Programs</h3><p>Global exposure and case-study based learning approach.</p>",
            "courses": ["MBA", "BBA", "Digital Marketing"]
        }
    ]

    for data in colleges_data:
        college, created = College.objects.get_or_create(
            slug=data['slug'],
            defaults={
                'name': data['name'],
                'description': data['description'],
                'website_content': data['content']
            }
        )
        if created:
            print(f"Created college: {college.name}")
            for c_name in data['courses']:
                Course.objects.create(college=college, name=c_name, description=f"Comprehensive course in {c_name}")
                print(f"  - Added course: {c_name}")

if __name__ == "__main__":
    seed_data()
