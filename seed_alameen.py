"""
Seed data for Al-Ameen Engineering College (slug: alameen).

Al-Ameen Engineering College is run by Al-Ameen Educational Trust in Kulappully,
Shornur, Palakkad, Kerala. It offers seven B.Tech branches, two M.Tech programmes,
and undergraduate BCA/BBA programmes (affiliated to APJ Abdul Kalam Technological
University, approved by AICTE). The course/add-on spreadsheet supplied for this
admission portal ("ADD_ON_DETAILS_AL_AMEEN.xlsx") only listed industry specializations
for the BCA and BBA programmes; the full course catalogue below (all 11 programmes)
was taken from the college's own website (alameen.edu.in) so every B.Tech and M.Tech
branch is represented, with specializations attached only where the spreadsheet named
them.

Run with: python manage.py shell < seed_alameen.py
(This mirrors the project's existing seed_nirmala.py / seed_eranad.py convention.)
"""

from admission_system.models import College, Course, AddonCourse

BANK_DETAILS = (
    "Bank: HDFC Bank\n"
    "Account Name: Badger Skills International Pvt Ltd\n"
    "Account Number: 50200090517560\n"
    "IFSC: HDFC0000436\n"
    "Branch: Perinthalmanna"
)

college, _ = College.objects.update_or_create(
    slug="alameen",
    defaults=dict(
        name="Al-Ameen Engineering College",
        description=(
            "Al-Ameen Engineering College, managed by Al-Ameen Educational Trust, has grown over "
            "twenty-one years into one of the fastest-growing engineering colleges in Palakkad "
            "district, offering B.Tech, M.Tech, BCA and BBA programmes from its campus in "
            "Kulappully, Shornur."
        ),
        website_content="",
        logo_url="https://alameen.edu.in/wp-content/uploads/2022/07/logo_eng_alameen.png",
        theme_color="#0A3A59",
        bank_details=BANK_DETAILS,
        payment_qr_image="college_qrs/alameen_payment_qr.png",
        upi_id="",
        upi_payee_name="Badger Skills International Pvt Ltd",
        address="Kulappully, Shornur, Palakkad, Kerala",
        affiliation=(
            "Approved by AICTE; Affiliated to APJ Abdul Kalam Technological University (KTU); "
            "NAAC accredited institution"
        ),
        email="admin@alameencollege.com",
        phone="+91 99461 06370",
        website="https://alameen.edu.in/",
    ),
)

COURSES = [
    ("B.Tech Electronics & Communication Engineering",
     "Signal processing, communication systems and embedded electronics across the B.Tech curriculum.", 60, []),
    ("B.Tech Electrical & Electronics Engineering",
     "Power systems, electrical machines and control engineering fundamentals.", 60, []),
    ("B.Tech Mechanical Engineering",
     "Design, thermal systems and manufacturing processes for mechanical engineers.", 60, []),
    ("B.Tech Civil Engineering",
     "Structural design, construction technology and infrastructure engineering.", 60, []),
    ("B.Tech Computer Science & Engineering",
     "Software engineering, data structures and systems programming.", 60, []),
    ("B.Tech Computer Science & Engineering (Cyber Security)",
     "Core computer science paired with a security-first specialization track.", 60, []),
    ("B.Tech Artificial Intelligence & Data Science",
     "Machine learning, data engineering and applied artificial intelligence.", 60, []),
    ("BCA (Bachelor of Computer Applications)",
     "A three-year computing degree with a choice of modern specializations.", 60,
     ["AI & ML", "Cloud Computing", "Ethical Hacking & Cyber Security"]),
    ("BBA (Bachelor of Business Administration)",
     "Business fundamentals with management specializations in growing sectors.", 60,
     ["Aviation & Airport Management", "Logistics & Supply Chain Management"]),
    ("M.Tech Electronics & Communication Engineering",
     "Postgraduate research and advanced coursework in communication engineering.", 18, []),
    ("M.Tech Electrical & Electronics Engineering",
     "Postgraduate specialization in power systems and electrical engineering.", 18, []),
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
