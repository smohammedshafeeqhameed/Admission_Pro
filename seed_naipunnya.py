"""
Seed script for Naipunnya School of Management, Cherthala (NSM).

Creates/updates the College row (slug="naipunnya") together with its courses and
addon courses for the 2027 admission batch, matching COURSE_DETAILS.pdf and the
college's real letterhead/payment details. Follows the same update_or_create
convention as seed_nirmala.py / seed_royalcet.py so it can be re-run safely.

Run with:
    python manage.py shell < seed_naipunnya.py

Requires migration 0022_college_letterhead_fields to be applied first
(adds address/affiliation/email/phone/website to College).
"""

from admission_system.models import College, Course, AddonCourse

BANK_DETAILS = """Account Name: Badger Skills International Pvt Ltd
Bank: HDFC Bank
Account Number: 50200089696154
IFSC Code: HDFC0001552
Branch: Thrissur Eastfort"""

college, _ = College.objects.update_or_create(
    slug="naipunnya",
    defaults={
        "name": "Naipunnya School of Management, Cherthala",
        "description": (
            "Naipunnya School of Management, Cherthala, is a NAAC A-grade institution "
            "affiliated to the University of Kerala, run as a project of the Archdiocese "
            "of Ernakulam-Angamaly. It offers undergraduate programmes across arts, "
            "business, computing and commerce, built around professionalism, discipline "
            "and holistic student development."
        ),
        "theme_color": "#1B2E63",
        "logo_url": "https://naipunnyacollege.ac.in/wp-content/uploads/2026/07/Naipunnya-MC-logo-final-horizontal-scaled.png",
        "affiliation": "Affiliated to University of Kerala; NAAC Accredited Grade A; AICTE Approved; ISO 21001:2018 Certified",
        "address": "Near Manorama Junction, Cherthala, Alappuzha, Kerala - 688524",
        "phone": "+91 86068 02255",
        "email": "info@naipunnyacollege.ac.in",
        "website": "https://naipunnyacollege.ac.in/",
        "bank_details": BANK_DETAILS,
        "upi_payee_name": "Badger Skills International Pvt Ltd",
        "payment_qr_image": "college_qrs/naipunnya_payment_qr.png",
    },
)

COURSES = [
    (
        "BA English (Language & Communicative English)",
        "A three-year undergraduate degree in English language and literature with a "
        "strong communicative-English component.",
        [("addon", "Logistics and Supply Chain Management")],
    ),
    (
        "BBA (Bachelor of Business Administration)",
        "A three-year undergraduate management degree covering business fundamentals, "
        "leadership and organisational behaviour.",
        [("addon", "ACCA (Association of Chartered Certified Accountants)")],
    ),
    (
        "BCA (Bachelor of Computer Applications)",
        "A three-year undergraduate degree in computer applications covering "
        "programming, data structures, databases and modern software development.",
        [("addon", "Cyber Security & Ethical Hacking")],
    ),
    (
        "B.Sc Computer Science",
        "A three-year undergraduate science degree in computer science covering core "
        "programming, algorithms and systems concepts.",
        [("addon", "AI & Machine Learning")],
    ),
    (
        "B.Com - Travel & Tourism",
        "A three-year undergraduate commerce degree with a specialization in travel "
        "and tourism management.",
        [],
    ),
    (
        "B.Com - Finance",
        "A three-year undergraduate commerce degree with a specialization in finance.",
        [],
    ),
    (
        "B.Com - Taxation",
        "A three-year undergraduate commerce degree with a specialization in direct "
        "and indirect taxation.",
        [],
    ),
]

for name, description, addons in COURSES:
    course, _ = Course.objects.update_or_create(
        college=college,
        name=name,
        defaults={"description": description, "total_seats": 60},
    )
    for _, addon_name in addons:
        AddonCourse.objects.get_or_create(course=course, name=addon_name)

print(f"Seeded college: {college.name} (slug={college.slug})")
print(f"Courses: {', '.join(c.name for c in college.courses.all())}")
