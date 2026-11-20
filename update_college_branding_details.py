"""
One-off script to fill in College.address / phone / email / website /
affiliation for the application-form letterhead (admission_system/models.py,
pdf_template.html), for the colleges that already have a real logo_url and
theme_color configured.

Run once, AFTER applying migration 0022_college_letterhead_fields:

    python manage.py migrate
    python manage.py shell < update_college_branding_details.py

Contact details below were collected from public college-directory listings
(the colleges' own sites, Careers360, CollegeDunia, CollegeBatch, etc.) in
Nov 2026. They're a starting point, not guaranteed current -- please check
and correct them in Django Admin -> Colleges. A few fields that couldn't be
confidently confirmed were left blank on purpose rather than guessed; fill
those in directly in the admin.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ams_project.settings')
django.setup()

from admission_system.models import College

details = {
    "ymbc": {
        "address": "Marian Village, Puthuppady P.O., Kothamangalam - Muvattupuzha Highway, Ernakulam, Kerala - 686691",
        "phone": "0485-2826772, 9846877776",
        "email": "",
        "website": "https://ymbc.edu.in",
        "affiliation": "Affiliated to Mahatma Gandhi University, Kottayam",
    },
    "elims": {
        "address": "Ponganamkad, Kurichikkara P.O., Thrissur, Kerala - 680028",
        "phone": "0487-2694201",
        "email": "elimsmgt@gmail.com",
        "website": "https://elims.edu.in",
        "affiliation": "Affiliated to University of Calicut | Approved by AICTE",
    },
    "alshifa": {
        "address": "Keezhattur, Perinthalmanna, Malappuram, Kerala - 679325",
        "phone": "",
        "email": "",
        "website": "https://www.alshifacollegeofartsandscience.ac.in",
        "affiliation": "",
    },
    "alazhar": {
        "address": "Al-Azhar Campus, Perumpillichira, Thodupuzha, Idukki, Kerala - 685605",
        "phone": "9496911119",
        "email": "",
        "website": "https://alazharthodupuzha.org",
        "affiliation": "Affiliated to MG University, Kottayam | KUHS, Thrissur | KTU, Thiruvananthapuram",
    },
    "nirmala": {
        "address": "Nirmala College P.O., Muvattupuzha, Ernakulam, Kerala - 686661",
        "phone": "9446600852",
        "email": "",
        "website": "https://nirmalacollege.ac.in",
        "affiliation": "Affiliated to Mahatma Gandhi University, Kottayam | NAAC A++ Accredited",
    },
    "jbcmet": {
        "address": "JB Campus, Arackappady, Vengola P.O., Perumbavoor, Ernakulam, Kerala - 683556",
        "phone": "0484-2655001",
        "email": "engg@jaibharathcollege.com",
        "website": "https://www.jaibharathcollege.com",
        "affiliation": "Affiliated to Mahatma Gandhi University, Kottayam",
    },
    "mes-kunnukara": {
        "address": "Kunnukara P.O., Aluva, Ernakulam, Kerala - 683578",
        "phone": "",
        "email": "",
        "website": "http://www.mescollegekunnukara.org",
        "affiliation": "Affiliated to Mahatma Gandhi University, Kottayam",
    },
}

print("Updating college branding/contact details...")
updated = 0
for slug, data in details.items():
    try:
        c = College.objects.get(slug=slug)
    except College.DoesNotExist:
        print(f"  Skipped (not found): {slug}")
        continue
    for field, value in data.items():
        if value:
            setattr(c, field, value)
    c.save()
    print(f"  Updated: {c.name}")
    updated += 1

print(f"Done. Updated {updated} colleges. Review/correct in Django Admin -> Colleges.")
