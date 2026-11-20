"""
Seed script for Royal College of Engineering & Technology (RCET), Akkikavu, Thrissur.

Creates/updates the College row (slug="royalcet") together with its courses and
addon courses for the 2027 admission batch, matching the data in
ROYAL_COLLEGE_2027_BATCH_COURSES.xlsx and the college's real letterhead/payment
details. Follows the same update_or_create convention as seed_nirmala.py /
seed_alazhar.py so it can be re-run safely.

Run with:
    python manage.py shell < seed_royalcet.py
or:
    python manage.py runscript seed_royalcet   (if django-extensions is installed)

Requires migration 0022_college_letterhead_fields to be applied first
(adds address/affiliation/email/phone/website to College) - run
`python manage.py migrate` before this script if you haven't already.
"""

from admission_system.models import College, Course, AddonCourse

BANK_DETAILS = """Account Name: Royal College of Engineering and Technology
Bank: (as per the shared bank details screenshot)
Account Number: (as per the shared bank details screenshot)
IFSC Code: (as per the shared bank details screenshot)
UPI ID: (as per the shared bank details screenshot)"""

college, _ = College.objects.update_or_create(
    slug="royalcet",
    defaults={
        "name": "Royal College of Engineering & Technology",
        "description": (
            "Royal College of Engineering & Technology (RCET), Akkikavu, Thrissur, is a "
            "NAAC-accredited engineering college affiliated to the APJ Abdul Kalam "
            "Technological University (KTU), offering undergraduate programmes across a "
            "21-acre campus with modern labs, an active Innovation & Entrepreneurship "
            "Development Cell, and a dedicated placement team."
        ),
        "theme_color": "#1C2A4A",
        "logo_url": "https://royalcet.ac.in/wp-content/uploads/2022/04/small-logo.png",
        "affiliation": "Affiliated to APJ Abdul Kalam Technological University (KTU); Approved by AICTE; NAAC Accredited",
        "address": "Chiramanangad P.O., Akkikavu, Thrissur, Kerala - 680604",
        "phone": "+91 90485 99995",
        "email": "info@royalcet.ac.in",
        "website": "https://royalcet.ac.in/",
        "bank_details": BANK_DETAILS,
        "upi_payee_name": "Royal College of Engineering and Technology",
        "payment_qr_image": "college_qrs/royalcet_payment_qr.png",
    },
)

bca, _ = Course.objects.update_or_create(
    college=college,
    name="BCA (Bachelor of Computer Applications)",
    defaults={
        "description": (
            "A three-year undergraduate degree in computer applications covering "
            "programming, data structures, databases and modern software development."
        ),
        "total_seats": 60,
    },
)

bba, _ = Course.objects.update_or_create(
    college=college,
    name="BBA (Bachelor of Business Administration)",
    defaults={
        "description": (
            "A three-year undergraduate management degree covering business "
            "fundamentals, finance and organisational behaviour."
        ),
        "total_seats": 60,
    },
)

for course, addon_name in [
    (bca, "AI & ML"),
    (bca, "Cyber Security & Ethical Hacking"),
    (bba, "Aviation and Airport Management"),
    (bba, "Logistics and Supply Chain Management"),
]:
    AddonCourse.objects.get_or_create(course=course, name=addon_name)

print(f"Seeded college: {college.name} (slug={college.slug})")
print(f"Courses: {', '.join(c.name for c in college.courses.all())}")
