import logging
import re
from datetime import datetime

import requests
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


def is_username_taken(username):
    """Case-insensitive check for whether a username is already in use."""
    return User.objects.filter(username__iexact=username).exists()


def suggest_unique_username(username, max_attempts=1000):
    """
    Given a desired username that is already taken, suggest a free
    alternative using a regex-based numeric-suffix strategy.

    If the username already ends in digits (e.g. "johndoe42"), that
    numeric suffix is split off with a regex and incremented until a
    free username is found. Otherwise, digits starting at 1 are appended
    (e.g. "johndoe" -> "johndoe1", "johndoe2", ...).

    Returns the first free candidate username, or None if nothing opened
    up within max_attempts (practically never happens).
    """
    match = re.match(r'^(.*?)(\d+)$', username)
    if match:
        base, start = match.group(1), int(match.group(2)) + 1
    else:
        base, start = username, 1

    for counter in range(start, start + max_attempts):
        candidate = f"{base}{counter}"
        if not is_username_taken(candidate):
            return candidate
    return None


def send_payment_slip_email(application):
    """
    Sends a professional payment receipt email to the student
    after the finance manager approves the payment.
    
    Args:
        application: The Application model instance with payment_status='Success'
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    student = application.student
    college = application.college
    course = application.course

    # Generate a receipt number: APR-{college_id}-{app_id}-{timestamp}
    receipt_number = f"APR-{college.id:03d}-{application.id:05d}-{datetime.now().strftime('%Y%m%d')}"

    # Build context for the email template
    context = {
        'student_name': student.name,
        'student_email': student.email,
        'student_phone': student.phone,
        'college_name': college.name,
        'course_name': course.name,
        'addon_course': application.addon_course or '',
        'transaction_id': application.transaction_id or 'N/A',
        'amount_paid': f"{float(application.amount_paid):,.2f}",
        'payment_date': datetime.now().strftime('%d %B %Y, %I:%M %p'),
        'receipt_number': receipt_number,
        'theme_color': college.theme_color or '#6366f1',
        'current_year': datetime.now().year,
    }

    # Render HTML email
    html_message = render_to_string('admission_system/payment_slip_email.html', context)
    plain_message = strip_tags(html_message)

    subject = f"Payment Receipt - {college.name} | {course.name}"

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[student.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Payment slip email sent to {student.email} for application #{application.id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send payment slip email to {student.email}: {e}")
        return False


def get_cre_referral_link(cre_profile, college, request=None):
    """
    Builds a CRE's unique referral link for a given college
    (apply/<college_slug>/<username>/<cre_id>/), as an absolute URL.

    Uses `request.build_absolute_uri()` when a request is available
    (e.g. the admin dashboard "Allocate" view), so the scheme/host match
    whatever domain the action was performed on. Falls back to the
    `SITE_URL` setting (e.g. when allocation happens through the Django
    /admin/ page, where no request is threaded through to the signal).
    """
    path = reverse('apply_admission', kwargs={
        'college_slug': college.slug,
        'username': cre_profile.user.username,
        'cre_id': cre_profile.cre_id,
    })
    if request is not None:
        return request.build_absolute_uri(path)
    site_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    return f"{site_url}{path}" if site_url else path


def normalize_whatsapp_number(phone):
    """
    Normalizes a phone number into the digits-only, country-code-prefixed
    format WhatsApp's Cloud API expects for the `to` field (e.g.
    '917736043497'). Assumes a bare 10-digit number is Indian (+91),
    since that's this project's primary market - adjust here if CREs
    outside India start registering.
    """
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return None
    if len(digits) == 10:
        digits = '91' + digits
    elif len(digits) == 11 and digits.startswith('0'):
        digits = '91' + digits[1:]
    return digits


def send_whatsapp_message(to_phone, template_params, template_name=None, lang_code=None):
    """
    Sends a WhatsApp message via Meta's WhatsApp Cloud API, from the
    business number configured as WHATSAPP_PHONE_NUMBER_ID.

    Uses a pre-approved message TEMPLATE rather than a free-form text
    message: Meta's Cloud API requires an approved template for any
    business-initiated message sent outside the 24-hour customer-service
    window (i.e. any message that isn't a reply to something the
    recipient sent first), which is the case here. The template named by
    WHATSAPP_TEMPLATE_NAME must already exist and be approved in Meta
    Business Manager before this will work, with one body placeholder
    per entry in `template_params` (in order).

    Requires WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID to be
    configured (see settings.py / .env); logs and returns False rather
    than raising if they're missing, so a misconfigured WhatsApp
    integration never blocks the allocation itself.
    """
    access_token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', None)
    phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', None)
    if not access_token or not phone_number_id:
        logger.warning(
            "WhatsApp not configured (missing WHATSAPP_ACCESS_TOKEN/"
            "WHATSAPP_PHONE_NUMBER_ID); skipping message to %s", to_phone
        )
        return False

    normalized = normalize_whatsapp_number(to_phone)
    if not normalized:
        logger.warning("Invalid WhatsApp number, skipping: %r", to_phone)
        return False

    template_name = template_name or getattr(settings, 'WHATSAPP_TEMPLATE_NAME', 'cre_college_allocated')
    lang_code = lang_code or getattr(settings, 'WHATSAPP_TEMPLATE_LANG', 'en_US')

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": normalized,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in template_params],
                }
            ],
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("WhatsApp message sent to %s via template '%s'", normalized, template_name)
        return True
    except Exception as e:
        body = getattr(getattr(e, 'response', None), 'text', '')
        logger.error("Failed to send WhatsApp message to %s: %s %s", normalized, e, body)
        return False


def notify_cre_college_allocated(cre_profile, college, request=None):
    """
    Notifies a CRE by email and WhatsApp that they've been allocated to a
    college, including their unique referral link for it.

    Wired up via the `m2m_changed` signal on CREProfile.allocated_colleges
    (see models.py), so this fires for every newly-added college whether
    the allocation was made from the custom admin-dashboard "Allocate"
    form or the Django /admin/ CREProfile page's college picker.

    Missing contact details (no email, or no phone) skip that channel
    only, rather than failing the whole allocation.
    """
    referral_link = get_cre_referral_link(cre_profile, college, request=request)
    user = cre_profile.user
    results = {'email': False, 'whatsapp': False}
    cre_name = user.get_full_name() or user.username

    if user.email:
        context = {
            'cre_name': cre_name,
            'college_name': college.name,
            'referral_link': referral_link,
            'theme_color': college.theme_color or '#6366f1',
            'current_year': datetime.now().year,
        }
        html_message = render_to_string('admission_system/cre_college_allocated_email.html', context)
        plain_message = strip_tags(html_message)
        try:
            send_mail(
                subject=f"You've been allocated to {college.name}",
                message=plain_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or settings.EMAIL_HOST_USER,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            results['email'] = True
            logger.info("Allocation email sent to %s for college %s", user.email, college.name)
        except Exception as e:
            logger.error("Failed to send allocation email to %s: %s", user.email, e)
    else:
        logger.warning("CRE %s has no email on file; skipping allocation email", user.username)

    if cre_profile.phone:
        results['whatsapp'] = send_whatsapp_message(
            cre_profile.phone,
            template_params=[cre_name, college.name, referral_link],
        )
    else:
        logger.warning("CRE %s has no phone on file; skipping WhatsApp notification", user.username)

    return results
