from django.db import models, transaction
from django.db.models import F
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from .validators import validate_photo

class College(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    website_content = models.TextField(help_text="HTML content for the college static page")
    theme_color = models.CharField(max_length=7, default="#6366f1", help_text="HEX color code for institutional branding")
    logo_url = models.URLField(blank=True, null=True, help_text="URL to the institution's logo")
    
    # Custom Payment Settings
    upi_id = models.CharField(max_length=255, blank=True, null=True, help_text="Specific UPI ID for this college (e.g., college@sbi)")
    upi_payee_name = models.CharField(max_length=255, blank=True, null=True, help_text="Payee name for UPI (e.g., ABC College)")
    payment_qr_image = models.ImageField(upload_to="college_qrs/", blank=True, null=True, help_text="Upload static QR code image (if empty, dynamic QR is shown using UPI ID)")
    bank_details = models.TextField(blank=True, null=True, help_text="Bank Account Number, IFSC Code, Account Name, etc.")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Course(models.Model):
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=255)
    description = models.TextField()

    # Seat tracking for the Campus Manager portal's Admit action. These
    # live directly on Course (not per academic year) - set/reset
    # total_seats from the Django admin at the start of each intake cycle.
    # occupied_seats is only ever changed by Application.admit() via an
    # atomic F() update; don't edit it by hand.
    total_seats = models.PositiveIntegerField(
        default=0,
        help_text="Total intake capacity for this course. Leave 0 if seats aren't tracked yet."
    )
    occupied_seats = models.PositiveIntegerField(
        default=0,
        help_text="Seats filled by admitted students. Updated automatically when a student is admitted - don't edit directly."
    )

    class Meta:
        unique_together = ('college', 'name')

    def __str__(self):
        return f"{self.name} - {self.college.name}"

    @property
    def available_seats(self):
        """Seats left to fill. Never negative, even if occupied_seats was
        ever pushed past total_seats (e.g. capacity lowered after admits)."""
        return max(self.total_seats - self.occupied_seats, 0)

class AddonCourse(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='addon_courses')
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.name} (Addon for {self.course.name})"

class CREProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cre_profile')
    cre_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    phone = models.CharField(max_length=15, blank=True)
    is_approved = models.BooleanField(default=False, help_text="Admin approval status for dashboard access")
    allocated_colleges = models.ManyToManyField(College, blank=True, related_name='assigned_cres')
    
    def __str__(self):
        return f"CRE: {self.user.username}"

class FinanceProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='finance_profile')
    phone = models.CharField(max_length=15, blank=True)
    
    def __str__(self):
        return f"Finance Manager: {self.user.username}"

class CampusManagerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='campus_manager_profile')
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='managers')
    phone = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return f"Campus Manager: {self.user.username} ({self.college.name})"

class Student(models.Model):
    GENDER_CHOICES = [('', '----------'), ('M', 'Male'), ('F', 'Female'), ('O', 'Other')]
    BLOOD_GROUP_CHOICES = [('', '----------'), ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'), ('O+', 'O+'), ('O-', 'O-'), ('AB+', 'AB+'), ('AB-', 'AB-')]
    
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    aadhar_number = models.CharField(max_length=12, null=True, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES, null=True, blank=True)
    category = models.CharField(max_length=50, null=True, blank=True)
    
    permanent_address = models.TextField(null=True, blank=True)
    correspondence_address = models.TextField(null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    
    father_name = models.CharField(max_length=255, null=True, blank=True)
    father_mobile = models.CharField(max_length=15, null=True, blank=True)
    father_occupation = models.CharField(max_length=255, null=True, blank=True)
    
    mother_name = models.CharField(max_length=255, null=True, blank=True)
    mother_mobile = models.CharField(max_length=15, null=True, blank=True)
    mother_occupation = models.CharField(max_length=255, null=True, blank=True)
    
    guardian_name = models.CharField(max_length=255, null=True, blank=True)
    guardian_mobile = models.CharField(max_length=15, null=True, blank=True)
    preferred_contact = models.CharField(max_length=50, choices=[('Student', 'Student'), ('Parent', 'Parent'), ('Guardian', 'Guardian')], default='Student')

    # Passport-size photo, shown across the Super Admin portal. Nullable so
    # existing students (applied before this field existed) don't break;
    # the application form makes it mandatory for new submissions.
    photo = models.ImageField(
        upload_to='student_photos/',
        null=True, blank=True,
        validators=[validate_photo],
        help_text="Passport-size photo (JPEG/PNG, max 2MB, passport-style portrait dimensions)"
    )

    def __str__(self):
        return self.name

class ApplicationSource(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

from django.core.exceptions import ValidationError


class AcademicYear(models.Model):
    """
    A single academic year/session (e.g. "2026-2027"), configured by the
    Django admin with a start and end date. This is the global period
    used across every portal dashboard to slice performance data: cards,
    seat/enrollment counts, revenue, and student lists are all scoped by
    matching Application.applied_at against [start_date, end_date].

    See utils.resolve_selected_academic_year and
    views.AcademicYearFilterMixin for how a request's selected year is
    resolved and applied to querysets.
    """
    name = models.CharField(max_length=20, unique=True, help_text='e.g. "2026-2027"')
    start_date = models.DateField(help_text="First day of this academic year.")
    end_date = models.DateField(help_text="Last day of this academic year.")
    is_current = models.BooleanField(
        default=False,
        help_text=(
            "Manual fallback only. The portal automatically treats the "
            "academic year whose start/end date contains today as current; "
            "this flag is only used as a fallback when no year's date range "
            "covers today (e.g. a gap between two years)."
        )
    )

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({'end_date': "End date must be after the start date."})
        if self.start_date and self.end_date:
            overlapping = AcademicYear.objects.filter(
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            clash = overlapping.first()
            if clash:
                raise ValidationError(
                    f"This date range overlaps with another academic year ({clash})."
                )

    @classmethod
    def get_current(cls):
        """
        The 'current' academic year: the one whose [start_date, end_date]
        contains today, if any; otherwise the one manually flagged
        is_current=True; otherwise the most recently-started year;
        otherwise None if no academic years have been configured yet.
        """
        today = timezone.localdate()
        ay = cls.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if ay:
            return ay
        ay = cls.objects.filter(is_current=True).first()
        if ay:
            return ay
        return cls.objects.order_by('-start_date').first()


class Application(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Pending Verification', 'Pending Verification'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
        ('Rejected', 'Rejected')
    ]

    STATUS_CHOICES = [
        ('Applied', 'Applied'),
        ('Admitted', 'Admitted'),
        ('Removed', 'Removed'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='applications')
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='applications')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='applications')
    addon_course = models.CharField(max_length=255, blank=True, null=True)
    source = models.CharField(max_length=255, null=True, blank=True, verbose_name="Reference Source")
    referred_by = models.ForeignKey(CREProfile, on_delete=models.SET_NULL, null=True, related_name='referrals')
    applied_at = models.DateTimeField(auto_now_add=True)

    # Admission status, set by the Campus Manager portal's "Admit" action
    # (see admit() below). closed_by is the staff member (typically the
    # campus manager) who performed that action - the "Counselor / Staff
    # member responsible for closing the lead".
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Applied')
    closed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='closed_applications',
        help_text="Staff member who admitted/closed this application."
    )
    admitted_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='removed_applications',
        help_text="Staff member who removed this student from the course (e.g. after a TC)."
    )
    removed_at = models.DateTimeField(null=True, blank=True)
    
    # Documents
    doc_10th = models.FileField(upload_to='documents/10th/', null=True, blank=True)
    doc_11th = models.FileField(upload_to='documents/11th/', null=True, blank=True)
    doc_12th = models.FileField(upload_to='documents/12th/', null=True, blank=True)
    doc_aadhar = models.FileField(upload_to='documents/aadhar/', null=True, blank=True)
    
    # Payment
    payment_status = models.CharField(max_length=25, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True, help_text="Google Pay Transaction Ref ID")
    payment_screenshot = models.ImageField(upload_to='payments/screenshots/', null=True, blank=True, help_text="Screenshot of the successful payment")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Commission workflow:
    #   1. Campus Manager marks an Admitted application "Eligible for
    #      Commission" (mark_eligible_for_commission below). This is what
    #      makes the "Apply for Commission" button appear for the
    #      referring CRE on their dashboard.
    #   2. The CRE who referred the student clicks "Apply for Commission"
    #      (apply_for_commission below), moving commission_status to
    #      'Pending' and sending it to the Finance Manager's Commission
    #      Applications dashboard.
    #   3. The Finance Manager approves or rejects it (approve_commission /
    #      reject_commission below).
    COMMISSION_STATUS_CHOICES = [
        ('Not Applied', 'Not Applied'),
        ('Pending', 'Pending Review'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    eligible_for_commission = models.BooleanField(
        default=False,
        help_text="Set by the Campus Manager once a student is admitted. Makes the 'Apply for Commission' action visible to the referring CRE."
    )
    eligible_for_commission_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commission_eligibility_marks',
        help_text="Campus Manager who marked this application eligible for commission."
    )
    eligible_for_commission_at = models.DateTimeField(null=True, blank=True)

    commission_status = models.CharField(max_length=20, choices=COMMISSION_STATUS_CHOICES, default='Not Applied')
    commission_applied_at = models.DateTimeField(null=True, blank=True)
    commission_reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commission_reviews',
        help_text="Finance Manager who approved/rejected this commission application."
    )
    commission_reviewed_at = models.DateTimeField(null=True, blank=True)
    commission_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Amount approved by the Finance Manager to be paid to the referring CRE, entered when approving the commission application."
    )

    class Meta:
        unique_together = ('student', 'college', 'course')

    def clean(self):
        # 1. Ensure the course belongs to the selected college
        if self.course and self.college and self.course.college != self.college:
            raise ValidationError({
                'course': f"The selected course '{self.course.name}' does not belong to '{self.college.name}'."
            })
        
        # 2. Duplicate Check
        if not self.pk:
            if Application.objects.filter(student=self.student, college=self.college, course=self.course).exists():
                raise ValidationError("This student has already applied for this course at this college.")

    def __str__(self):
        return f"{self.student.name} -> {self.college.name} ({self.course.name})"

    def admit(self, user=None):
        """
        Marks this application Admitted and atomically increments the
        course's occupied_seats by 1 (so available_seats drops by 1 right
        away for every other view reading it). Uses an F() expression
        rather than read-modify-write so concurrent admits across
        campus-manager sessions can't race each other into overcounting
        seats.

        Returns False without doing anything if the application was
        already admitted, so calling this twice (e.g. a double-submitted
        form) never double-deducts a seat.
        """
        if self.status == 'Admitted':
            return False
        with transaction.atomic():
            self.status = 'Admitted'
            self.closed_by = user
            self.admitted_at = timezone.now()
            # Clear any earlier removal record - this is a fresh admit (or a
            # re-admit of a previously Removed application), so the old
            # "Removed By" details no longer describe the current state.
            self.removed_by = None
            self.removed_at = None
            self.save(update_fields=['status', 'closed_by', 'admitted_at', 'removed_by', 'removed_at'])
            Course.objects.filter(pk=self.course_id).update(occupied_seats=F('occupied_seats') + 1)
        return True

    def unadmit(self, user=None):
        """
        Reverses admit() - for when an admitted student leaves the course
        (e.g. takes a transfer certificate) and their seat needs to go
        back into the pool. Sets status to 'Removed' and atomically
        decrements the course's occupied_seats by 1, using the same
        F()-expression pattern as admit() to stay race-safe.

        Returns False without doing anything if the application isn't
        currently Admitted, so this can't be used to free a seat that
        was never actually taken.

        closed_by/admitted_at are left untouched so "Admitted By" stays
        visible as history even after removal; removed_by/removed_at
        record who performed the removal and when, for a "Removed By"
        column alongside it.
        """
        if self.status != 'Admitted':
            return False
        with transaction.atomic():
            self.status = 'Removed'
            self.removed_by = user
            self.removed_at = timezone.now()
            self.save(update_fields=['status', 'removed_by', 'removed_at'])
            Course.objects.filter(pk=self.course_id, occupied_seats__gt=0).update(occupied_seats=F('occupied_seats') - 1)
        return True

    def mark_eligible_for_commission(self, user=None):
        """
        Campus Manager action: flags this (already Admitted) application as
        eligible for commission, which is what makes the "Apply for
        Commission" button appear on the referring CRE's dashboard.

        Returns False without doing anything if the application isn't
        currently Admitted, or if it's already marked eligible, so the
        button can't be double-submitted into clobbering the original
        marked-by/marked-at record.
        """
        if self.status != 'Admitted' or self.eligible_for_commission:
            return False
        self.eligible_for_commission = True
        self.eligible_for_commission_by = user
        self.eligible_for_commission_at = timezone.now()
        self.save(update_fields=['eligible_for_commission', 'eligible_for_commission_by', 'eligible_for_commission_at'])
        return True

    def apply_for_commission(self):
        """
        CRE action: submits this application's commission for Finance
        Manager review. Only possible once the Campus Manager has marked
        it eligible, and only from the 'Not Applied' or 'Rejected' state
        (a Rejected application can be re-submitted; an already
        Pending/Approved one can't be re-applied for).
        """
        if not self.eligible_for_commission or self.commission_status not in ('Not Applied', 'Rejected'):
            return False
        self.commission_status = 'Pending'
        self.commission_applied_at = timezone.now()
        self.commission_reviewed_by = None
        self.commission_reviewed_at = None
        self.save(update_fields=['commission_status', 'commission_applied_at', 'commission_reviewed_by', 'commission_reviewed_at'])
        return True

    def approve_commission(self, user=None, amount=None):
        """
        Finance Manager action: approves a Pending commission application,
        recording the payout amount entered in the approval pop-up as
        commission_amount.
        """
        if self.commission_status != 'Pending':
            return False
        self.commission_status = 'Approved'
        self.commission_reviewed_by = user
        self.commission_reviewed_at = timezone.now()
        self.commission_amount = amount
        self.save(update_fields=['commission_status', 'commission_reviewed_by', 'commission_reviewed_at', 'commission_amount'])
        return True

    def reject_commission(self, user=None):
        """Finance Manager action: rejects a Pending commission application."""
        if self.commission_status != 'Pending':
            return False
        self.commission_status = 'Rejected'
        self.commission_reviewed_by = user
        self.commission_reviewed_at = timezone.now()
        self.save(update_fields=['commission_status', 'commission_reviewed_by', 'commission_reviewed_at'])
        return True


from django.db.models.signals import m2m_changed
from django.dispatch import receiver


@receiver(m2m_changed, sender=CREProfile.allocated_colleges.through)
def _notify_cre_on_college_allocation(sender, instance, action, pk_set, **kwargs):
    """
    Fires whenever colleges are added to a CRE's allocated_colleges -
    whether that happens via the custom admin-dashboard "Allocate" view
    (AdminAllocateCollegeView) or the Django /admin/ CREProfile page's
    college picker (filter_horizontal). Sends the CRE an email + WhatsApp
    message with their referral link for each newly-added college.

    Both call sites stash the current request on the CREProfile instance
    as `_notification_request` before saving, so the referral link can be
    built as an absolute URL; it's optional (see
    utils.get_cre_referral_link's SITE_URL fallback).
    """
    if action != 'post_add' or not pk_set:
        return
    from .utils import notify_cre_college_allocated
    request = getattr(instance, '_notification_request', None)
    for college in College.objects.filter(pk__in=pk_set):
        notify_cre_college_allocated(instance, college, request=request)
