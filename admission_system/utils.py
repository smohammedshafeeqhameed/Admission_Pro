import logging
from datetime import datetime

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


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
