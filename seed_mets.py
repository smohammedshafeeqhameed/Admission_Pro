"""
Seed data for MET'S College of Advanced Studies (slug: mets).

MET'S College of Advanced Studies is part of MET'S Group of Institutions, administered
by Mala Educational Trust (established 2001), in Kuruvilassery, Mala, Thrissur, Kerala.
It offers six approved degree programmes affiliated to the University of Calicut.

The course/add-on spreadsheet supplied for this admission portal ("METS_COLLEGE.xlsx")
listed four programme buckets (BBA, BCA, B.Sc AI, B.Com) with add-on specializations.
The college's own website (metscas.ac.in) shows "B.Com" as three distinct named degrees
(Finance, Computer Application, Co-Operation), each with its own course page, so those
three are modelled as separate Course rows here -- all three carry the same three B.Com
add-ons from the spreadsheet (ACCA 9-paper exemption, Aviation & Airport Management,
Logistics & Supply Chain Management), since the spreadsheet did not distinguish between
the three B.Com streams. This assumption is worth double-checking against how the real
admission office actually offers these add-ons.

Note: no live, verifiable external logo URL could be found for this college (the site's
robots.txt blocks automated fetching and no direct image URL could be extracted), so
College.logo_url is left blank here -- only the static-file logo used in the bespoke
template is populated. Add a logo_url manually via Admin if one is available.

Run with: python manage.py shell < seed_mets.py
(This mirrors the project's existing seed_nirmala.py / seed_eranad.py / seed_alameen.py convention.)
"""

from admission_system.models import College, Course, AddonCourse

BANK_DETAILS = (
    "Bank: HDFC Bank Ltd\n"
    "Account Name: Badger Skills International Pvt Ltd\n"
    "Account Number: 50200079212880\n"
    "IFSC: HDFC0001518\n"
    "Branch: Perumbavoor"
)

college, _ = College.objects.update_or_create(
    slug="mets",
    defaults=dict(
        name="MET'S College of Advanced Studies",
        description=(
            "MET'S College of Advanced Studies, part of MET'S Group of Institutions, is administered by "
            "Mala Educational Trust (established 2001) in Kuruvilassery, Mala, Thrissur, offering six "
            "approved degree programmes affiliated to the University of Calicut."
        ),
        website_content="",
        logo_url="",
        theme_color="#332878",
        bank_details=BANK_DETAILS,
        payment_qr_image="college_qrs/mets_payment_qr.png",
        upi_id="",
        upi_payee_name="Badger Skills International Pvt Ltd",
        address="Kuruvilassery P.O., Mala, Thrissur, Kerala - 680735",
        affiliation=(
            "Affiliated to University of Calicut; administered by Mala Educational Trust, part of MET'S "
            "Group of Institutions"
        ),
        email="mets@metscas.ac.in",
        phone="+91 80868 42047",
        website="https://metscas.ac.in/",
    ),
)

BCOM_ADDONS = ["ACCA (9 Paper Exemption)", "Aviation & Airport Management", "Logistics & Supply Chain Management"]
AI_ADDONS = ["Artificial Intelligence & Machine Learning", "Cloud Computing", "Ethical Hacking & Cyber Security"]

COURSES = [
    ("B.Com (Finance)",
     "Commerce fundamentals with a finance specialization, under University of Calicut.", 50, BCOM_ADDONS),
    ("B.Com (Computer Application)",
     "Commerce fundamentals paired with computer application coursework.", 50, BCOM_ADDONS),
    ("B.Com (Co-Operation)",
     "Commerce fundamentals with a co-operation and allied-sector specialization.", 50, BCOM_ADDONS),
    ("BBA",
     "Business administration fundamentals with a marketing-led specialization.", 50,
     ["Aviation & Airport Management", "Logistics & Supply Chain Management"]),
    ("BCA",
     "A three-year computing degree under University of Calicut.", 50, AI_ADDONS),
    ("B.Sc Artificial Intelligence",
     "A science degree focused on artificial intelligence and applied computing.", 50, AI_ADDONS),
]

for name, description, total_seats, addons in COURSES:
    course, _ = Course.objects.update_or_create(
        college=college,
        name=name,
        defaults=dict(description=description, total_seats=total_seats),
    )
    for addon_name in addons:
        AddonCourse.objects.get_or_create(course=course, name=addon_name)

print(f"Seeded {college.name} (slug={college.slug}) with {len(COURSES)} courses.")
