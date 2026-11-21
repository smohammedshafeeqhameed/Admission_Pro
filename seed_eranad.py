"""
Seed script for Eranad Knowledge City College of Commerce & Science (EKCCS).

Creates/updates the College row (slug="eranad") together with its courses and
addon courses for the 2027-28 admission batch, matching
Eranad_Courses_2027_28.xlsx and the college's real letterhead/payment details.
Follows the same update_or_create convention as seed_nirmala.py / seed_royalcet.py
/ seed_naipunnya.py so it can be re-run safely.

Run with:
    python manage.py shell < seed_eranad.py

Requires migration 0022_college_letterhead_fields to be applied first
(adds address/affiliation/email/phone/website to College).

Note: Eranad Knowledge City (ekc.edu.in) is an umbrella campus of four
institutions (Technical Campus, College of Architecture, College of Commerce
& Science, Public School). The 2027-28 course list (BBA/BCA/BSc CS/BCom)
matches the College of Commerce & Science (ekccs.edu.in), so that is the
specific institution this college entry represents, under the parent EKC
branding supplied for the admission portal.
"""

from admission_system.models import College, Course, AddonCourse

BANK_DETAILS = """Account Name: Badger Skills International Pvt Ltd
Bank: HDFC Bank
Account Number: 50200090517560
IFSC Code: HDFC0000436
Branch: Perinthalmanna"""

college, _ = College.objects.update_or_create(
    slug="eranad",
    defaults={
        "name": "Eranad Knowledge City College of Commerce & Science",
        "description": (
            "Eranad Knowledge City College of Commerce & Science sits inside a 100-acre "
            "campus set up by Al-Hind Educational & Charitable Trust in Cherukulam, "
            "Manjeri. It offers undergraduate programmes in business, computing and "
            "commerce, built around academic excellence and innovative thinking."
        ),
        "theme_color": "#15181B",
        "logo_url": "https://i0.wp.com/ekc.edu.in/wp-content/uploads/2022/07/ekc-logo.png?fit=484%2C278&ssl=1",
        "affiliation": "Part of Eranad Knowledge City, a 100-acre campus set up by Al-Hind Educational & Charitable Trust",
        "address": "Eranad Knowledge City, Cherukulam, Manjeri, Malappuram District, Kerala - 676122",
        "phone": "+91 96565 00040",
        "email": "office@ekc.edu.in",
        "website": "https://ekccs.edu.in/",
        "bank_details": BANK_DETAILS,
        "upi_payee_name": "Badger Skills International Pvt Ltd",
        "payment_qr_image": "college_qrs/eranad_payment_qr.png",
    },
)

COURSES = [
    (
        "BBA (Bachelor of Business Administration)",
        "A three-year undergraduate management degree covering business fundamentals, "
        "leadership and organisational behaviour.",
        ["Aviation & Airport Management", "Logistics & Supply Chain Management"],
    ),
    (
        "BCA (Bachelor of Computer Applications)",
        "A three-year undergraduate degree in computer applications covering "
        "programming, data structures, databases and modern software development.",
        ["Artificial Intelligence & Machine Learning", "Cloud Computing, Ethical Hacking & Cyber Security"],
    ),
    (
        "B.Sc Computer Science",
        "A three-year undergraduate science degree in computer science covering core "
        "programming, algorithms and systems concepts.",
        ["Artificial Intelligence & Machine Learning", "Cloud Computing, Ethical Hacking & Cyber Security"],
    ),
    (
        "B.Com (Bachelor of Commerce)",
        "A three-year undergraduate commerce degree covering accounting, finance and "
        "business administration fundamentals.",
        ["Aviation & Airport Management", "Logistics & Supply Chain Management", "ACCA (9 Paper Exemption)"],
    ),
]

for name, description, addons in COURSES:
    course, _ = Course.objects.update_or_create(
        college=college,
        name=name,
        defaults={"description": description, "total_seats": 60},
    )
    for addon_name in addons:
        AddonCourse.objects.get_or_create(course=course, name=addon_name)

print(f"Seeded college: {college.name} (slug={college.slug})")
print(f"Courses: {', '.join(c.name for c in college.courses.all())}")
