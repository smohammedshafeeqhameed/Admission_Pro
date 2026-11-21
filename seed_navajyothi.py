"""
Seed data for Navajyothi College Cherupuzha (slug: navajyothi).

Run with: python manage.py shell < seed_navajyothi.py
(or paste into `python manage.py shell`)

Source materials:
  - Course/add-on spreadsheet: NAVAJYOTHI_COLLEGE.xlsx
  - College website: https://njc.ac.in/
  - Logo: shield emblem + modern wordmark, "LIGHTED TO ENLIGHTEN"
  - Payment screenshot: HDFC Bank Ltd, A/C 50200079212880, IFSC HDFC0001518,
    Branch Perumbavoor (note: these exact bank details are also used for
    MET'S College of Advanced Studies -- flagged to the user as a recurring
    reused-payment-account pattern across colleges, worth double-checking).

Course modelling note:
  The spreadsheet lists five programme buckets (BBA, BCOM, BCA, BSW,
  BSC PSYCHOLOGY) each with 1-3 add-on specializations, joined by commas
  within a cell where more than one applies. Unlike MET'S College, nothing
  found on the college's own site contradicted treating "BCOM" as a single
  course, so it is modelled as one Course row (not split into variants).

Logo note:
  Unlike MET'S (where no live external logo URL could be verified), this
  college's root page fetched cleanly and returned a direct, live logo URL
  (https://njc.ac.in/public/img/logo/logo.webp), confirmed by loading it
  directly. College.logo_url is set to that real URL here. The user's
  uploaded logo file is also copied into the project's own static directory
  for the prominent hero placement on the admission page.
"""

from admission_system.models import College, Course, AddonCourse

college, _ = College.objects.update_or_create(
    slug="navajyothi",
    defaults=dict(
        name="Navajyothi College Cherupuzha",
        description=(
            "An academic initiative of the CST Fathers of the Little Flower "
            "Congregation in Cherupuzha, Kannur -- self-financed and affiliated "
            "to Kannur University since 2010, NAAC accredited with Grade B++."
        ),
        website_content=(
            "Navajyothi College, Cherupuzha carries the motto \"Lighted to "
            "Enlighten\". Facilities include a library, computer lab, "
            "reprographic center, career training center and canteen, with "
            "student support through the Students Union, NSS, Placement Cell "
            "and Counselling services."
        ),
        logo_url="https://njc.ac.in/public/img/logo/logo.webp",
        theme_color="#0B4DA8",
        bank_details=(
            "HDFC Bank Ltd, Account Number 50200079212880, IFSC HDFC0001518, "
            "Branch Perumbavoor"
        ),
        payment_qr_image="college_qrs/navajyothi_payment_qr.png",
        upi_id="",
        upi_payee_name="Navajyothi College Cherupuzha",
        address="P.B No. 5, Cherupuzha P.O, Kannur - 670511",
        affiliation="Affiliated to Kannur University",
        email="navajyothicst@gmail.com",
        phone="+914985240540",
        website="https://njc.ac.in/",
    ),
)

COURSES = [
    (
        "BBA",
        "Bachelor of Business Administration -- business fundamentals with a "
        "choice of industry specializations.",
        [
            "Aviation & Airport Management",
            "Logistics & Supply Chain Management",
            "Hospital Administration",
        ],
    ),
    (
        "B.Com",
        "Bachelor of Commerce -- commerce fundamentals with a choice of "
        "professional specializations.",
        [
            "ACCA (9 Paper Exemption)",
            "Aviation & Airport Management",
            "Logistics & Supply Chain Management",
        ],
    ),
    (
        "BCA",
        "Bachelor of Computer Applications -- a three-year computing degree "
        "under Kannur University.",
        ["Artificial Intelligence & Data Science"],
    ),
    (
        "BSW",
        "Bachelor of Social Work -- social work fundamentals with a "
        "healthcare-sector specialization.",
        ["Hospital Administration"],
    ),
    (
        "B.Sc Psychology",
        "A science degree in Psychology with a healthcare-sector "
        "specialization.",
        ["Hospital Administration"],
    ),
]

for name, description, addons in COURSES:
    course, _ = Course.objects.update_or_create(
        college=college,
        name=name,
        defaults=dict(description=description, total_seats=60, occupied_seats=0),
    )
    for addon_name in addons:
        AddonCourse.objects.get_or_create(course=course, name=addon_name)

print(f"Seeded {college.name} ({college.slug}) with {len(COURSES)} courses.")
