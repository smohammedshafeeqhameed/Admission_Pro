"""
Seed data for Malabar College of Engineering & Technology (slug: malabarcet).

Run with: python manage.py shell < seed_malabarcet.py
(or paste into `python manage.py shell`)

Source materials:
  - Course/add-on spreadsheet: MALABAR_COLLEGE.xlsx
  - College website: https://malabarcet.ac.in/
  - Logo: sail/ribbon mark (blue, green, red) + "mcet" wordmark + full name
    + NBA accreditation seal
  - Payment screenshot: HDFC Bank Ltd, A/C 50200079212880, IFSC HDFC0001518,
    Branch Perumbavoor (note: these exact bank details, and the "Badger
    Skills International" payee label, are also used for MET'S College of
    Advanced Studies and Navajyothi College Cherupuzha -- this is now the
    third college in a row sharing one payment account; worth confirming
    this is intentional).

Course modelling note:
  The spreadsheet lists "BTECH" with five named branches (Computer Science
  & Engineering, Artificial Intelligence & Machine Learning, Biomedical
  Engineering, Mechatronics Engineering, Electronics & Computer
  Engineering). As with Al-Ameen's B.Tech branches, these are modelled as
  five separate Course rows rather than add-ons of one generic "B.Tech"
  course, since each is a distinct named engineering degree with no
  further specialization choice.

  BBA and BCA each list genuine add-on specializations in the spreadsheet
  and are modelled as a single Course row each, with their add-ons as
  AddonCourse rows. The BCA cell "CLOUD COMPUTING, ETHICAL HACKING & CYBER
  SECURITY" is split into two separate add-ons on the established
  comma-splitting heuristic (confirmed identical in Al-Ameen's and MET'S's
  spreadsheets).

  The spreadsheet did not list the college's M.Tech programmes at all, but
  the college's own website menu shows two: M.Tech Environmental
  Engineering and M.Tech Computer Science Engineering. Both are added here
  as additional Course rows (no add-ons, matching the Al-Ameen precedent of
  completing the catalogue from the website when the spreadsheet is
  partial) -- flagged here as an assumption worth the user double-checking.

Logo note:
  Unlike MET'S, a live, direct logo URL was found and verified on the
  college's own site (https://malabarcet.ac.in/assets/img/logo.png), so
  College.logo_url is set to that real URL.
"""

from admission_system.models import College, Course, AddonCourse

college, _ = College.objects.update_or_create(
    slug="malabarcet",
    defaults=dict(
        name="Malabar College of Engineering & Technology",
        description=(
            "Founded in 2009 by Dr. K S Hamza and run by the IQRA Education & "
            "Charitable Trust, MCET is an AICTE-approved engineering college in "
            "Desamangalam, Thrissur, with NBA accreditation for its Computer "
            "Science and Mechatronics Engineering branches."
        ),
        website_content=(
            "Malabar College of Engineering & Technology carries the motto "
            "\"Better Education For Better World\". The Desamangalam campus "
            "offers a library, hostel, canteen, sports facilities and "
            "transportation alongside its classrooms and labs."
        ),
        logo_url="https://malabarcet.ac.in/assets/img/logo.png",
        theme_color="#0094D6",
        bank_details=(
            "HDFC Bank Ltd, Account Number 50200079212880, IFSC HDFC0001518, "
            "Branch Perumbavoor"
        ),
        payment_qr_image="college_qrs/malabarcet_payment_qr.png",
        upi_id="",
        upi_payee_name="Malabar College of Engineering & Technology",
        address="Desamangalam, Pallur (PO), Cheruthuruthy, Thrissur - 679532",
        affiliation="Affiliated to APJ Abdul Kalam Technological University",
        email="",
        phone="+919495161111",
        website="https://malabarcet.ac.in/",
    ),
)

COURSES = [
    (
        "Computer Science Engineering",
        "B.Tech branch -- NBA accredited, APJAKTU affiliated.",
        [],
    ),
    (
        "Artificial Intelligence & Machine Learning",
        "B.Tech branch in AI and machine learning systems.",
        [],
    ),
    (
        "Biomedical Engineering",
        "B.Tech branch combining engineering with healthcare technology.",
        [],
    ),
    (
        "Mechatronics Engineering",
        "B.Tech branch -- NBA accredited, blending mechanical, electronic and "
        "computer engineering.",
        [],
    ),
    (
        "Electronics & Computer Engineering",
        "B.Tech branch spanning electronics and computing.",
        [],
    ),
    (
        "BBA",
        "Bachelor of Business Administration -- business fundamentals with a "
        "choice of industry specializations.",
        ["Aviation & Airport Management", "Logistics & Supply Chain Management"],
    ),
    (
        "BCA",
        "Bachelor of Computer Applications -- a three-year computing degree "
        "under APJAKTU.",
        [
            "Artificial Intelligence & Data Science",
            "Cloud Computing",
            "Ethical Hacking & Cyber Security",
        ],
    ),
    (
        "M.Tech Environmental Engineering",
        "Postgraduate programme in environmental engineering.",
        [],
    ),
    (
        "M.Tech Computer Science Engineering",
        "Postgraduate programme in computer science engineering.",
        [],
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
