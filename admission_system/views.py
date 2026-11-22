import os
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count, Sum, Min
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
from django.views import View
from django.views.generic import CreateView, TemplateView
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from .forms import CRERegistrationForm, StudentAdmissionForm
from .models import CREProfile, College, Application, Student, Course
import csv
from django.http import HttpResponse, Http404
import boto3
from django.conf import settings
from django.utils.text import slugify
from django.http import JsonResponse
from .models import AddonCourse, CampusManagerProfile
from django.template.loader import get_template
from .utils import is_username_taken, suggest_unique_username


class CampusManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return hasattr(self.request.user, 'campus_manager_profile')

def get_addon_courses(request):
    course_id = request.GET.get('course_id')
    if course_id:
        addons = AddonCourse.objects.filter(course_id=course_id).values('id', 'name')
        return JsonResponse(list(addons), safe=False)
    return JsonResponse([], safe=False)

class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

class ExecutiveRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        # Executive access is granted purely by linking a CREProfile to an
        # ExecutiveProfile from the Django admin (see ExecutiveProfile in
        # models.py) - deliberately not tied to is_superuser, and not
        # checked on request.user directly, since there is no separate
        # Executive login: it's always "this CRE account, promoted".
        return is_executive_user(self.request.user)


def is_executive_user(user):
    """
    True iff `user` is a CRE account whose CREProfile has been linked to
    an ExecutiveProfile from the Django admin. Shared by
    ExecutiveRequiredMixin, the login/dashboard redirect logic, and the
    CRE-approval gate below (an executive doesn't need separate CRE
    approval - being promoted here is itself the approval).
    """
    cre_profile = getattr(user, 'cre_profile', None)
    return bool(cre_profile and hasattr(cre_profile, 'executive_profile'))

class AcademicYearFilterMixin:
    """
    Resolves the globally-selected Academic Year (see
    utils.resolve_selected_academic_year) once per request and:

    - exposes it as `self.academic_year` (an AcademicYear or None) so a
      view's get_context_data/get can scope its own querysets with
      `self.academic_year_date_filter(...)`;
    - injects `academic_years` (all, for the dropdown), `selected_academic_year`,
      and `current_academic_year_id` into the template context, so the
      Academic Year filter in base.html has what it needs on every
      portal page that mixes this in.

    Mix this into any dashboard/portal View or TemplateView; it does not
    change behaviour for a view that doesn't call academic_year_date_filter.
    """
    def dispatch(self, request, *args, **kwargs):
        from .models import AcademicYear
        from .utils import resolve_selected_academic_year
        self.academic_year = resolve_selected_academic_year(request)
        self.current_academic_year = AcademicYear.get_current()
        return super().dispatch(request, *args, **kwargs)

    def academic_year_date_filter(self, field_path='applied_at'):
        from .utils import academic_year_date_filter as _build_filter
        return _build_filter(self.academic_year, field_path)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import AcademicYear
        context['academic_years'] = AcademicYear.objects.all()
        context['selected_academic_year'] = self.academic_year
        context['current_academic_year_id'] = self.current_academic_year.id if self.current_academic_year else None
        return context

class AdminDashboardView(AcademicYearFilterMixin, SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        search_query = self.request.GET.get('search', '')
        college_id = self.request.GET.get('college', '')

        cres = CREProfile.objects.select_related('user').prefetch_related('allocated_colleges').order_by('-user__date_joined')

        if search_query:
            cres = cres.filter(
                Q(user__username__icontains=search_query) |
                Q(phone__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )

        if college_id:
            cres = cres.filter(allocated_colleges__id=college_id)

        pending_cres = CREProfile.objects.filter(is_approved=False).select_related('user').order_by('-user__date_joined')

        # Students/applications are scoped to the selected academic year
        # (by Application.applied_at); CRE/college counts are catalog
        # totals and stay global - they aren't a per-year "performance"
        # metric the way enrollments/revenue are.
        total_students = Student.objects.filter(**self.academic_year_date_filter('applications__applied_at')).distinct().count()
        total_applications = Application.objects.filter(**self.academic_year_date_filter('applied_at')).count()

        context.update({
            'total_students': total_students,
            'total_cres': CREProfile.objects.count(),
            'total_colleges': College.objects.count(),
            'total_applications': total_applications,
            'all_cres': cres.distinct(),
            'pending_cres': pending_cres,
            'pending_count': pending_cres.count(),
            'all_colleges': College.objects.all(),
            'search_query': search_query,
            'selected_college': int(college_id) if college_id and college_id.isdigit() else None,
            'is_dashboard': True
        })
        return context

class AdminAllocateCollegeView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        cre_id = request.POST.get('cre_id')
        college_ids = request.POST.getlist('colleges')
        cre_profile = get_object_or_404(CREProfile, id=cre_id)
        # Stashed so the m2m_changed signal (models.py) can build an
        # absolute referral-link URL for the allocation email/WhatsApp
        # notification; see get_cre_referral_link in utils.py.
        cre_profile._notification_request = request
        cre_profile.allocated_colleges.set(college_ids)
        messages.success(request, f"Colleges updated for {cre_profile.user.username}")
        return redirect('admin_dashboard')

class AdminApproveCREView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        cre_id = request.POST.get('cre_id')
        action = request.POST.get('action') # 'approve' or 'suspend'
        cre_profile = get_object_or_404(CREProfile, id=cre_id)
        
        if action == 'approve':
            cre_profile.is_approved = True
            messages.success(request, f"Partner {cre_profile.user.username} approved successfully!")
        else:
            cre_profile.is_approved = False
            messages.warning(request, f"Partner {cre_profile.user.username} suspended.")
            
        cre_profile.save()
        return redirect('admin_dashboard')

class AdminCREDetailView(AcademicYearFilterMixin, SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_cre_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cre_id = self.kwargs.get('pk')
        cre_profile = None
        if cre_id:
            cre_profile = get_object_or_404(CREProfile, id=cre_id)

        # All referrals (students applied through this CRE), scoped to the
        # selected academic year
        referrals = Application.objects.filter(
            referred_by=cre_profile, **self.academic_year_date_filter('applied_at')
        ).select_related('student', 'college', 'course').order_by('-applied_at')
        
        context.update({
            'cre': cre_profile,
            'referrals': referrals,
            'total_referrals': referrals.count(),
            'successful_referrals': referrals.filter(payment_status='Success').count(),
            'pending_referrals': referrals.filter(payment_status__in=['Pending', 'Pending Verification']).count(),
            'is_dashboard': True
        })
        return context

class HowItWorksView(TemplateView):
    template_name = 'admission_system/how_it_works.html'

class BenefitsView(TemplateView):
    template_name = 'admission_system/benefits.html'

class SupportView(TemplateView):
    template_name = 'admission_system/support.html'

class AdminCollegeListView(AcademicYearFilterMixin, SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_college_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # student_count is a per-year "seat" metric (applications in the
        # selected academic year); course_count is a catalog total and
        # stays global.
        colleges = College.objects.annotate(
            student_count=Count(
                'applications', distinct=True,
                filter=Q(**self.academic_year_date_filter('applications__applied_at'))
            ),
            course_count=Count('courses', distinct=True)
        )
        context['colleges'] = colleges
        context['is_dashboard'] = True
        return context

class AdminCollegeDetailView(AcademicYearFilterMixin, SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_college_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        college_id = self.kwargs.get('pk')
        college = get_object_or_404(College, id=college_id)
        courses = college.courses.all().annotate(
            applicant_count=Count(
                'applications',
                filter=Q(**self.academic_year_date_filter('applications__applied_at'))
            ),
            admitted_count=Count(
                'applications',
                filter=Q(
                    applications__status='Admitted',
                    **self.academic_year_date_filter('applications__applied_at')
                )
            )
        )

        context.update({
            'college': college,
            'courses': courses,
            'total_students': Application.objects.filter(
                college=college, **self.academic_year_date_filter('applied_at')
            ).count(),
            'is_dashboard': True
        })
        return context

class AdminCourseStudentListView(AcademicYearFilterMixin, SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_course_student_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)

        applications = Application.objects.filter(
            course=course, **self.academic_year_date_filter('applied_at')
        ).select_related('student', 'college', 'referred_by__user', 'closed_by', 'removed_by').order_by('-applied_at')

        context.update({
            'course': course,
            'college': course.college,
            'applications': applications,
            'total_enrollments': applications.count(),
            'successful_enrollments': applications.filter(payment_status='Success').count(),
            'pending_enrollments': applications.filter(payment_status='Pending').count(),
            'admitted_count': applications.filter(status='Admitted').count(),
            'is_dashboard': True
        })
        return context

class AdminStudentDetailView(AcademicYearFilterMixin, SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_student_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        app_id = self.kwargs.get('app_id')
        application = get_object_or_404(Application.objects.select_related('student', 'college', 'course', 'referred_by__user'), id=app_id)
        
        context.update({
            'app': application,
            'student': application.student,
            'is_dashboard': True
        })
        return context

@login_required
def download_application_document(request, app_id, doc_field):
    if not request.user.is_superuser:
        messages.error(request, "Permission denied.")
        return redirect('home')
        
    application = get_object_or_404(Application, id=app_id)
    doc_file = getattr(application, doc_field, None)
    
    if not doc_file or not hasattr(doc_file, 'name') or not doc_file.name:
        messages.error(request, "File not found.")
        return redirect('admin_student_detail', app_id=app_id)

    # Friendly name for the download
    ext = doc_file.name.split('.')[-1]
    name_slug = slugify(application.student.name)
    doc_label = doc_field.replace('doc_', '').replace('_', ' ')
    filename = f"{name_slug}_{doc_label}.{ext}"

    from django.core.files.storage import default_storage
    try:
        url = default_storage.url(
            doc_file.name,
            parameters={'ResponseContentDisposition': f'attachment; filename="{filename}"'}
        )
        return redirect(url)
    except Exception as e:
        messages.error(request, f"Error generating download link: {e}")
        return redirect('admin_student_detail', app_id=app_id)


@login_required
def download_student_photo(request, app_id):
    """
    Forces a download of the student's passport-size photo. Scoped through
    the Application (app_id) - same as download_application_document - so
    Super Admin reaches it from the student profile page, even though the
    photo itself lives on Student, not Application.
    """
    if not request.user.is_superuser:
        messages.error(request, "Permission denied.")
        return redirect('home')

    application = get_object_or_404(Application, id=app_id)
    photo_file = application.student.photo

    if not photo_file or not hasattr(photo_file, 'name') or not photo_file.name:
        messages.error(request, "No photo on file for this student.")
        return redirect('admin_student_detail', app_id=app_id)

    ext = photo_file.name.split('.')[-1]
    name_slug = slugify(application.student.name)
    filename = f"{name_slug}_passport_photo.{ext}"

    from django.core.files.storage import default_storage
    try:
        url = default_storage.url(
            photo_file.name,
            parameters={'ResponseContentDisposition': f'attachment; filename="{filename}"'}
        )
        return redirect(url)
    except Exception as e:
        messages.error(request, f"Error generating download link: {e}")
        return redirect('admin_student_detail', app_id=app_id)

class FinanceRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or hasattr(self.request.user, 'finance_profile')

class FinanceDashboardView(AcademicYearFilterMixin, FinanceRequiredMixin, TemplateView):
    template_name = 'admission_system/finance_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        college_id = self.request.GET.get('college')
        ay_filter = self.academic_year_date_filter('applied_at')

        # Use a base queryset with select_related to avoid additional student/college/course lookups
        base_apps = Application.objects.select_related('student', 'college', 'course').filter(**ay_filter)

        # Pending verifications - prioritize these
        pending_apps = base_apps.filter(payment_status='Pending Verification')

        # History - limit to last 50 for performance
        history_apps = base_apps.exclude(payment_status__in=['Pending', 'Pending Verification']).order_by('-applied_at')

        if college_id:
            pending_apps = pending_apps.filter(college_id=college_id)
            history_apps = history_apps.filter(college_id=college_id)
            context['active_college'] = get_object_or_404(College, id=college_id)

        # Global Stats - Single aggregate query, scoped to the selected academic year
        stats = Application.objects.filter(payment_status='Success', **ay_filter).aggregate(
            total_revenue=Sum('amount_paid'),
            total_verified=Count('id')
        )
        total_revenue = stats['total_revenue'] or 0
        total_verified = stats['total_verified'] or 0

        # College Breakdown - Optimized with conditional annotation to replace N+1 loop
        rel_ay_filter = self.academic_year_date_filter('applications__applied_at')
        colleges_with_stats = College.objects.annotate(
            revenue=Sum('applications__amount_paid', filter=Q(applications__payment_status='Success', **rel_ay_filter)),
            app_count=Count('applications', filter=Q(applications__payment_status='Success', **rel_ay_filter))
        ).order_by('name')
        
        colleges_data = [
            {
                'college': college,
                'revenue': college.revenue or 0,
                'count': college.app_count
            }
            for college in colleges_with_stats
        ]
            
        context.update({
            'pending_apps': pending_apps,
            'history_apps': history_apps[:50],
            'pending_count': pending_apps.count(),
            'is_dashboard': True,
            'total_verified': total_verified,
            'total_revenue': total_revenue,
            'colleges_data': colleges_data,
            'all_colleges': colleges_with_stats,
        })
        return context


class FinanceCommissionDashboardView(AcademicYearFilterMixin, FinanceRequiredMixin, TemplateView):
    """
    Separate dashboard (inside the Finance Manager portal) listing every
    commission application submitted by a CRE - i.e. every Application
    with commission_status != 'Not Applied'. Pending ones surface first
    for review/approve/reject; once approved here they move to
    'Finance Approved' and sit in a read-only "Awaiting Executive
    Approval" section - Finance's own approval is a recommendation, not
    the final word (see Application.finance_approve_commission in
    models.py). Once the Executive gives the final sign-off from their
    own Commission Desk, an application lands back here as 'Approved'
    in the actionable "Ready to Settle" section, where the Finance
    Manager uploads the payment receipt/bill once the CRE has actually
    been paid (see Application.settle_commission in models.py). Only
    'Settled' and 'Rejected' applications - the truly terminal states -
    reach History below.
    """
    template_name = 'admission_system/finance_commission_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        college_id = self.request.GET.get('college')

        base_apps = Application.objects.select_related(
            'student', 'college', 'course', 'referred_by__user',
            'commission_reviewed_by', 'commission_executive_reviewed_by', 'commission_settled_by',
        ).exclude(commission_status='Not Applied')

        pending_apps = base_apps.filter(commission_status='Pending').order_by('commission_applied_at')
        awaiting_executive_apps = base_apps.filter(commission_status='Finance Approved').order_by('commission_reviewed_at')
        ready_to_settle_apps = base_apps.filter(commission_status='Approved').order_by('commission_executive_reviewed_at')
        reviewed_apps = base_apps.filter(commission_status__in=['Settled', 'Rejected']).order_by('-commission_reviewed_at')

        if college_id:
            pending_apps = pending_apps.filter(college_id=college_id)
            awaiting_executive_apps = awaiting_executive_apps.filter(college_id=college_id)
            ready_to_settle_apps = ready_to_settle_apps.filter(college_id=college_id)
            reviewed_apps = reviewed_apps.filter(college_id=college_id)
            context['active_college'] = get_object_or_404(College, id=college_id)

        context.update({
            'pending_commission_apps': pending_apps,
            'awaiting_executive_apps': awaiting_executive_apps,
            'ready_to_settle_apps': ready_to_settle_apps,
            'reviewed_commission_apps': reviewed_apps[:50],
            'pending_commission_count': pending_apps.count(),
            'awaiting_executive_count': awaiting_executive_apps.count(),
            'approved_commission_count': base_apps.filter(commission_status='Approved').count(),
            'settled_commission_count': base_apps.filter(commission_status='Settled').count(),
            'rejected_commission_count': base_apps.filter(commission_status='Rejected').count(),
            'all_colleges': College.objects.all().order_by('name'),
            'is_dashboard': True,
        })
        return context


class FinanceCommissionActionView(FinanceRequiredMixin, View):
    """
    Handles the Approve/Reject buttons on the Commission Applications
    dashboard. Delegates to Application.finance_approve_commission() /
    reject_commission() (models.py) so a Pending-only guard can't drift
    between call sites. Approving requires an "amount" field in the POST
    body - the payout entered by the Finance Manager in the "Approve
    Commission" pop-up (see finance_commission_dashboard.html) - which is
    recorded as Application.commission_amount. Approving here does not
    finalise the payout: it moves the application to 'Finance Approved'
    and onto the Executive's own Commission Desk for the last sign-off.
    """
    def post(self, request, *args, **kwargs):
        from decimal import Decimal, InvalidOperation

        application = get_object_or_404(Application.objects.select_related('student'), id=kwargs.get('app_id'))
        action = request.POST.get('action')

        if application.commission_status != 'Pending':
            messages.info(request, f"The commission application for {application.student.name} has already been reviewed.")
        elif action == 'approve':
            raw_amount = (request.POST.get('amount') or '').strip()
            try:
                amount = Decimal(raw_amount)
                if amount <= 0:
                    raise InvalidOperation
            except InvalidOperation:
                messages.error(request, "Enter a valid commission amount (greater than 0) before approving.")
                return redirect('finance_commission_dashboard')

            application.finance_approve_commission(user=request.user, amount=amount)
            messages.success(request, f"₹{amount} commission for {application.student.name} sent to the Executive for final approval.")
        elif action == 'reject':
            application.reject_commission(user=request.user)
            messages.warning(request, f"Commission rejected for {application.student.name}.")

        return redirect('finance_commission_dashboard')


class FinanceCommissionSettleView(FinanceRequiredMixin, View):
    """
    Handles the "Upload Receipt & Settle" action in the "Ready to
    Settle" section of the Commission Applications dashboard - the
    final step of the commission workflow. Only acts on an application
    the Executive has already given final sign-off to
    (commission_status == 'Approved'; see
    Application.executive_approve_commission in models.py), and
    requires a receipt/bill file in the request, which is what proves
    the CRE has actually been paid. Delegates the state change to
    Application.settle_commission() (models.py), which moves it to the
    truly terminal 'Settled' state - shown consistently from here on
    to the CRE, the Executive and the Finance Manager alike.
    """
    def post(self, request, *args, **kwargs):
        application = get_object_or_404(Application.objects.select_related('student'), id=kwargs.get('app_id'))
        receipt = request.FILES.get('receipt')

        if application.commission_status != 'Approved':
            messages.info(request, f"The commission application for {application.student.name} has already moved on.")
        elif not receipt:
            messages.error(request, "Attach the payment receipt or bill before settling this commission.")
        else:
            application.settle_commission(user=request.user, receipt=receipt)
            messages.success(request, f"Commission for {application.student.name} marked as settled. The transaction is now complete.")

        return redirect('finance_commission_dashboard')


class CampusManagerDashboardView(AcademicYearFilterMixin, CampusManagerRequiredMixin, TemplateView):
    template_name = 'admission_system/campus_manager_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manager_profile = self.request.user.campus_manager_profile
        college = manager_profile.college

        # Base Querysets for this campus, scoped to the selected academic year
        campus_apps = Application.objects.filter(
            college=college, **self.academic_year_date_filter('applied_at')
        ).select_related('student', 'course', 'referred_by', 'closed_by')
        success_apps = campus_apps.filter(payment_status='Success')
        
        # Stats
        total_apps = campus_apps.count()
        total_paid = success_apps.count()
        total_revenue = success_apps.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
        
        # Course-wise breakdown
        courses_data = []
        for course in college.courses.all():
            course_apps = campus_apps.filter(course=course)
            courses_data.append({
                'course': course,
                'total': course_apps.count(),
                'paid': course_apps.filter(payment_status='Success').count(),
                'revenue': course_apps.filter(payment_status='Success').aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
            })

        context.update({
            'college': college,
            'campus_apps': campus_apps.order_by('-applied_at'),
            'total_apps': total_apps,
            'total_paid': total_paid,
            'total_revenue': total_revenue,
            'courses_data': courses_data,
            'is_dashboard': True
        })
        return context

class CampusManagerExportCSVView(AcademicYearFilterMixin, CampusManagerRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        manager_profile = request.user.campus_manager_profile
        college = manager_profile.college
        course_id = request.GET.get('course_id')

        # Matches whichever academic year is currently selected on the
        # dashboard (resolved from the session by AcademicYearFilterMixin),
        # so the export always lines up with what's on screen.
        apps = Application.objects.filter(
            college=college, **self.academic_year_date_filter('applied_at')
        ).select_related('student', 'course', 'referred_by__user')
        
        if course_id:
            apps = apps.filter(course_id=course_id)
            course_name = apps.first().course.name if apps.exists() else 'students'
            safe_name = "".join([c for c in course_name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
            filename = f"{college.slug}_{safe_name.replace(' ', '_').lower()}_enrollments.csv"
        else:
            filename = f"{college.slug}_student_report.csv"
            
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Email', 'Phone', 'DOB', 'Gender', 'Aadhar Number', 'Blood Group',
            'Category', 'City', 'State', 'Father Name', 'Father Mobile', 
            'Course', 'Addon Course', 'Referred By', 'Reference', 'Payment Status', 'Applied Date'
        ])
        
        for app in apps:
            writer.writerow([
                app.student.name, 
                app.student.email,
                app.student.phone, 
                app.student.dob,
                app.student.gender,
                app.student.aadhar_number,
                app.student.blood_group,
                app.student.category,
                app.student.city,
                app.student.state,
                app.student.father_name,
                app.student.father_mobile,
                app.course.name,
                app.addon_course,
                app.referred_by.user.username if app.referred_by else "Direct",
                app.source,
                app.payment_status,
                app.applied_at.strftime('%Y-%m-%d %H:%M')
            ])
            
        return response

class CampusManagerCourseStudentListView(AcademicYearFilterMixin, CampusManagerRequiredMixin, TemplateView):
    """
    The dedicated Student List View opened by clicking a Course/Department
    card on the Campus Manager dashboard. Scoped to the manager's own
    college via get_object_or_404(..., college=manager_profile.college) so
    a manager can't view (or admit into) another campus's course by
    guessing a course_id in the URL.
    """
    template_name = 'admission_system/campus_manager_course_student_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manager_profile = self.request.user.campus_manager_profile
        course = get_object_or_404(Course, id=self.kwargs.get('course_id'), college=manager_profile.college)

        applications = Application.objects.filter(
            course=course, **self.academic_year_date_filter('applied_at')
        ).select_related('student', 'referred_by__user', 'closed_by', 'removed_by').order_by('-applied_at')

        context.update({
            'course': course,
            'college': manager_profile.college,
            'applications': applications,
            'total_applications': applications.count(),
            'admitted_count': applications.filter(status='Admitted').count(),
            'is_dashboard': True
        })
        return context


class CampusManagerUpdateSeatsView(CampusManagerRequiredMixin, View):
    """
    Lets a Campus Manager set their own course's seat capacity
    (Course.total_seats) directly from the portal, instead of needing
    Django admin access. occupied_seats is never touched here - it only
    ever moves via Application.admit()'s atomic F() update.
    """
    def post(self, request, *args, **kwargs):
        manager_profile = request.user.campus_manager_profile
        course = get_object_or_404(Course, id=kwargs.get('course_id'), college=manager_profile.college)

        raw_value = request.POST.get('total_seats', '').strip()
        try:
            total_seats = int(raw_value)
            if total_seats < 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Enter a valid, non-negative number of seats.")
            return redirect('campus_manager_course_student_list', course_id=course.id)

        course.total_seats = total_seats
        course.save(update_fields=['total_seats'])

        if total_seats < course.occupied_seats:
            messages.warning(
                request,
                f"{course.name}: capacity set to {total_seats}, which is below the {course.occupied_seats} students already admitted. "
                f"Available seats will show as 0 until capacity is raised again."
            )
        else:
            messages.success(request, f"Seat capacity for {course.name} updated to {total_seats}.")

        return redirect('campus_manager_course_student_list', course_id=course.id)


class CampusManagerAdmitStudentView(CampusManagerRequiredMixin, View):
    """
    Handles the "Admit" button on the course student list. Delegates the
    actual status change + atomic seat decrement to Application.admit()
    (models.py) so the same logic can't drift between call sites.
    """
    def post(self, request, *args, **kwargs):
        manager_profile = request.user.campus_manager_profile
        application = get_object_or_404(
            Application.objects.select_related('course', 'student'),
            id=kwargs.get('app_id'), college=manager_profile.college
        )

        if application.status == 'Admitted':
            messages.info(request, f"{application.student.name} is already admitted.")
        elif application.course.total_seats > 0 and application.course.available_seats <= 0:
            messages.error(
                request,
                f"No seats available in {application.course.name} - increase the seat capacity in Django admin to admit more students."
            )
        else:
            application.admit(user=request.user)
            messages.success(request, f"{application.student.name} has been admitted to {application.course.name}.")

        return redirect('campus_manager_course_student_list', course_id=application.course_id)


class CampusManagerRemoveStudentView(CampusManagerRequiredMixin, View):
    """
    Handles the "Remove" button that appears once a student is Admitted -
    covers cases like a student taking a transfer certificate and leaving
    the course. Delegates to Application.unadmit() (models.py) so the
    seat-freeing logic lives in exactly one place, same as admit().
    """
    def post(self, request, *args, **kwargs):
        manager_profile = request.user.campus_manager_profile
        application = get_object_or_404(
            Application.objects.select_related('course', 'student'),
            id=kwargs.get('app_id'), college=manager_profile.college
        )

        if application.status != 'Admitted':
            messages.info(request, f"{application.student.name} is not currently admitted.")
        else:
            application.unadmit(user=request.user)
            messages.success(
                request,
                f"{application.student.name} has been removed from {application.course.name}. The seat is available again."
            )

        return redirect('campus_manager_course_student_list', course_id=application.course_id)


class CampusManagerMarkCommissionEligibleView(CampusManagerRequiredMixin, View):
    """
    Handles the "Eligible for Commission" button on the course student
    list - shown next to an Admitted application. Delegates to
    Application.mark_eligible_for_commission() (models.py) so the same
    eligibility rules (must be Admitted, can't double-mark) live in one
    place. Marking an application eligible is what makes the "Apply for
    Commission" button appear on the referring CRE's dashboard.
    """
    def post(self, request, *args, **kwargs):
        manager_profile = request.user.campus_manager_profile
        application = get_object_or_404(
            Application.objects.select_related('course', 'student', 'referred_by__user'),
            id=kwargs.get('app_id'), college=manager_profile.college
        )

        if application.status != 'Admitted':
            messages.error(request, f"{application.student.name} must be admitted before being marked eligible for commission.")
        elif application.eligible_for_commission:
            messages.info(request, f"{application.student.name} is already eligible for commission.")
        else:
            application.mark_eligible_for_commission(user=request.user)
            if application.referred_by:
                messages.success(
                    request,
                    f"{application.student.name} marked eligible for commission. "
                    f"{application.referred_by.user.username} can now apply for commission from their dashboard."
                )
            else:
                messages.success(request, f"{application.student.name} marked eligible for commission.")

        return redirect('campus_manager_course_student_list', course_id=application.course_id)


class VerifyPaymentActionView(FinanceRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        from .utils import send_payment_slip_email
        
        app_id = request.POST.get('app_id')
        action = request.POST.get('action') # 'approve' or 'reject'
        
        app = get_object_or_404(Application, id=app_id)
        
        if action == 'approve':
            app.payment_status = 'Success'
            app.amount_paid = request.POST.get('amount_paid', 1500.00)
            app.save()
            
            # Send payment slip email to the student
            email_sent = send_payment_slip_email(app)
            if email_sent:
                messages.success(request, f"Payment verified for {app.student.name}. Receipt email sent to {app.student.email}.")
            else:
                messages.success(request, f"Payment verified for {app.student.name}.")
                messages.warning(request, f"Could not send receipt email to {app.student.email}. Please check email settings.")
        elif action == 'reject':
            app.payment_status = 'Rejected'
            app.save()
            messages.warning(request, f"Payment rejected for {app.student.name}")
            
        return redirect('finance_dashboard')

class AdminExportCSVView(AcademicYearFilterMixin, SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        export_type = request.GET.get('type', 'students')
        course_id = request.GET.get('course_id')

        if export_type == 'students':
            # Matches whichever academic year is currently selected on the
            # dashboard (resolved from the session by AcademicYearFilterMixin).
            apps = Application.objects.select_related(
                'student', 'college', 'course', 'referred_by__user'
            ).filter(**self.academic_year_date_filter('applied_at'))
            
            response = HttpResponse(content_type='text/csv')
            if course_id:
                apps = apps.filter(course_id=course_id)
                course_name = apps.first().course.name if apps.exists() else 'students'
                safe_name = "".join([c for c in course_name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                filename = f"{safe_name.replace(' ', '_').lower()}_enrollments.csv"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
            else:
                response['Content-Disposition'] = 'attachment; filename="students_report.csv"'
                
            writer = csv.writer(response)
            writer.writerow([
                'Name', 'Email', 'Phone', 'DOB', 'Gender', 'Aadhar Number', 'Blood Group',
                'Category', 'City', 'State', 'Father Name', 'Father Mobile', 'Applied College', 
                'Applied Course', 'Addon Course', 'Referred By', 'Reference', 'Payment Status', 'Applied Date'
            ])
            
            for app in apps:
                writer.writerow([
                    app.student.name, 
                    app.student.email, 
                    app.student.phone,
                    app.student.dob,
                    app.student.gender,
                    app.student.aadhar_number,
                    app.student.blood_group,
                    app.student.category,
                    app.student.city,
                    app.student.state,
                    app.student.father_name,
                    app.student.father_mobile,
                    app.college.name, 
                    app.course.name, 
                    app.addon_course,
                    app.referred_by.user.username if app.referred_by else 'Direct',
                    app.source,
                    app.payment_status,
                    app.applied_at.strftime('%Y-%m-%d')
                ])
            return response
        
        return redirect('admin_dashboard')

class CRERegistrationView(CreateView):
    template_name = 'admission_system/register.html'
    form_class = CRERegistrationForm
    success_url = reverse_lazy('cre_dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('cre_dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.save()
        CREProfile.objects.create(
            user=user,
            phone=form.cleaned_data.get('phone', '')
        )
        messages.success(self.request, "Account created successfully! Please wait for administrator approval before logging in.")
        return redirect('login')

class CRELoginView(LoginView):
    template_name = 'admission_system/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        remember_me = self.request.POST.get('remember_me')
        user = form.get_user()
        
        # Check if it's a CRE and if they are approved. A CRE promoted to
        # Executive (see ExecutiveProfile) skips this gate - being linked
        # there from the Django admin is itself the approval.
        cre_profile = getattr(user, 'cre_profile', None)
        if (cre_profile and not cre_profile.is_approved
                and not user.is_superuser and not is_executive_user(user)):
            from django.contrib.auth import logout
            logout(self.request)
            messages.error(self.request, "Your account is pending approval from the administrator.")
            return redirect('login')
            
        if not remember_me:
            # Set session to expire when browser closes
            self.request.session.set_expiry(0)
        else:
            # Set session to expire in 2 weeks
            self.request.session.set_expiry(1209600)  # 14 days in seconds
        return super().form_valid(form)

    def get_success_url(self):
        if is_executive_user(self.request.user):
            return reverse_lazy('executive_dashboard')
        if self.request.user.is_superuser:
            return reverse_lazy('admin_dashboard')
        if hasattr(self.request.user, 'finance_profile'):
            return reverse_lazy('finance_dashboard')
        if hasattr(self.request.user, 'campus_manager_profile'):
            return reverse_lazy('campus_manager_dashboard')
        return reverse_lazy('cre_dashboard')

class DashboardView(AcademicYearFilterMixin, LoginRequiredMixin, TemplateView):
    def get_template_names(self):
        if self.request.user.is_superuser:
            # We could have a separate admin dashboard if needed
            return ['admission_system/dashboard.html']
        return ['admission_system/dashboard.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        cre_profile = getattr(user, 'cre_profile', None)
        
        # If it's a superuser without a profile, create one for testing
        if not cre_profile and user.is_superuser:
            cre_profile, created = CREProfile.objects.get_or_create(user=user)
        
        if not cre_profile:
            context['no_profile'] = True
            return context

        if user.is_superuser:
            colleges = College.objects.all()
        else:
            colleges = cre_profile.allocated_colleges.all()
            
        referrals = Application.objects.filter(
            referred_by=cre_profile, **self.academic_year_date_filter('applied_at')
        ).order_by('-applied_at')

        context.update({
            'cre_profile': cre_profile,
            'colleges': colleges,
            'referrals': referrals,
            'total_referrals': referrals.count(),
            'base_url': self.request.build_absolute_uri('/')[:-1],
            'is_cre': True,
            'is_dashboard': True
        })
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Resolved once, up front: an Executive is a CRE account whose
            # CREProfile has been linked to an ExecutiveProfile from the
            # Django admin - checked before the finance/campus-manager
            # branches and before the CRE-approval gate below, since being
            # promoted here is itself the approval (see is_executive_user).
            cre_profile = getattr(request.user, 'cre_profile', None)
            if cre_profile and hasattr(cre_profile, 'executive_profile'):
                return redirect('executive_dashboard')

            if hasattr(request.user, 'finance_profile'):
                return redirect('finance_dashboard')

            if hasattr(request.user, 'campus_manager_profile'):
                return redirect('campus_manager_dashboard')

            if cre_profile and not cre_profile.is_approved and not request.user.is_superuser:
                from django.contrib.auth import logout
                logout(request)
                messages.error(request, "Your account is pending approval. Please contact the administrator.")
                return redirect('login')

            if not cre_profile and not request.user.is_superuser:
                messages.error(request, "This account is not registered as a CRE.")
                return render(request, 'admission_system/home.html', {'error': True})

        return super().dispatch(request, *args, **kwargs)


class CREApplyCommissionView(LoginRequiredMixin, View):
    """
    Handles the "Apply for Commission" button on the CRE dashboard's
    referral list. Only visible/actionable for the CRE who actually made
    the referral (filtered by referred_by=request.user.cre_profile below,
    so a CRE can't apply for commission on someone else's referral), and
    only once the Campus Manager has marked that application eligible.
    Delegates the actual state change to Application.apply_for_commission()
    (models.py), which is what puts it on the Finance Manager's Commission
    Applications dashboard.
    """
    def post(self, request, *args, **kwargs):
        cre_profile = getattr(request.user, 'cre_profile', None)
        if not cre_profile:
            messages.error(request, "Only CRE accounts can apply for commission.")
            return redirect('cre_dashboard')

        application = get_object_or_404(
            Application.objects.select_related('student'),
            id=kwargs.get('app_id'), referred_by=cre_profile
        )

        if not application.eligible_for_commission:
            messages.error(request, f"{application.student.name} has not been marked eligible for commission yet.")
        elif application.commission_status == 'Pending':
            messages.info(request, f"Your commission application for {application.student.name} is already pending review.")
        elif application.commission_status == 'Finance Approved':
            messages.info(request, f"Your commission application for {application.student.name} has been approved by Finance and is awaiting the Executive's final sign-off.")
        elif application.commission_status == 'Approved':
            messages.info(request, f"Your commission application for {application.student.name} has already been approved.")
        elif application.commission_status == 'Settled':
            messages.info(request, f"The commission for {application.student.name} has already been settled - the transaction is complete.")
        else:
            application.apply_for_commission()
            messages.success(request, f"Commission application for {application.student.name} submitted. The finance team will review it.")

        return redirect('cre_dashboard')


class ExecutiveDashboardView(AcademicYearFilterMixin, ExecutiveRequiredMixin, TemplateView):
    """
    The Executive Portal: one network-wide command center for whoever
    holds ExecutiveProfile (a CRE account promoted from the Django admin
    - see ExecutiveProfile in models.py) to see every institution,
    student, application, rupee and partner across the whole platform at
    a glance.

    Deliberately read-only and self-contained: every action (approving a
    partner, verifying a payment, admitting a student, approving a
    commission) still happens on the existing Admin / Finance / Campus
    Manager portals, but this page does not link out to them - an
    Executive-promoted CRE has no access to those role-gated views. This
    view only aggregates what those already record, scoped by the same
    selected Academic Year as every other dashboard (see
    AcademicYearFilterMixin).
    """
    template_name = 'admission_system/executive_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ay_filter = self.academic_year_date_filter('applied_at')
        apps_qs = Application.objects.filter(**ay_filter)

        # ---- Headline KPIs -------------------------------------------------
        total_students = Student.objects.filter(
            **self.academic_year_date_filter('applications__applied_at')
        ).distinct().count()
        total_applications = apps_qs.count()
        total_admitted = apps_qs.filter(status='Admitted').count()
        total_removed = apps_qs.filter(status='Removed').count()
        verified_revenue = apps_qs.filter(payment_status='Success').aggregate(
            total=Sum('amount_paid'))['total'] or 0
        pending_verification_count = apps_qs.filter(payment_status='Pending Verification').count()
        approved_commission_payout = apps_qs.filter(commission_status='Approved').aggregate(
            total=Sum('commission_amount'))['total'] or 0
        pending_commission_count = apps_qs.filter(commission_status='Pending').count()
        # Deliberately not scoped by apps_qs's Academic Year filter: this is
        # the Commission Desk's own actionable queue (see
        # ExecutiveCommissionDashboardView below), so the count on this tile
        # must always match what that portal actually shows, whichever
        # academic year happens to be selected here.
        awaiting_executive_commission_count = Application.objects.filter(commission_status='Finance Approved').count()

        total_colleges = College.objects.count()
        total_partners = CREProfile.objects.count()
        pending_partner_approvals = CREProfile.objects.filter(is_approved=False).count()

        seat_totals = Course.objects.aggregate(total=Sum('total_seats'), occupied=Sum('occupied_seats'))
        total_seats = seat_totals['total'] or 0
        occupied_seats = seat_totals['occupied'] or 0
        seat_utilization_pct = round((occupied_seats / total_seats) * 100, 1) if total_seats else 0

        attention_count = pending_partner_approvals + pending_verification_count + pending_commission_count

        # ---- Monthly trend (applications, admits, verified revenue) -------
        # Scoped to the selected Academic Year's own calendar so the chart
        # always matches the year picked in the filter bar; falls back to
        # the trailing 12 months when no Academic Year has been configured.
        if self.academic_year:
            trend_start = self.academic_year.start_date
            trend_end = self.academic_year.end_date
        else:
            today = timezone.localdate()
            trend_start = today.replace(day=1) - timedelta(days=365)
            trend_end = today

        monthly = list(
            Application.objects.filter(applied_at__date__gte=trend_start, applied_at__date__lte=trend_end)
            .annotate(month=TruncMonth('applied_at'))
            .values('month')
            .annotate(
                applications=Count('id'),
                revenue=Sum('amount_paid', filter=Q(payment_status='Success')),
                admitted=Count('id', filter=Q(status='Admitted')),
            )
            .order_by('month')
        )
        trend_labels = [m['month'].strftime('%b %Y') for m in monthly]
        trend_applications = [m['applications'] for m in monthly]
        trend_revenue = [float(m['revenue'] or 0) for m in monthly]
        trend_admitted = [m['admitted'] for m in monthly]

        # ---- Payment status breakdown --------------------------------------
        payment_status_colors = {
            'Success': '#0ca30c',
            'Pending': '#fab219',
            'Pending Verification': '#3987e5',
            'Failed': '#d03b3b',
            'Rejected': '#ec835a',
        }
        payment_breakdown = list(
            apps_qs.values('payment_status').annotate(count=Count('id')).order_by('-count')
        )
        max_payment_count = max((row['count'] for row in payment_breakdown), default=0)
        for row in payment_breakdown:
            row['color'] = payment_status_colors.get(row['payment_status'], '#9085e9')
            row['pct'] = round((row['count'] / max_payment_count) * 100, 1) if max_payment_count else 0

        # ---- Institution-wise breakdown -------------------------------------
        # Looped rather than one heavily-annotated queryset: each college
        # needs independent Sum()/Count() aggregates across two different
        # related sets (applications and courses), which a single annotated
        # queryset would fan out/duplicate across. Institution count is
        # small, so this stays cheap.
        institutions = []
        for college in College.objects.all():
            college_apps = Application.objects.filter(college=college, **ay_filter)
            seats = Course.objects.filter(college=college).aggregate(
                total=Sum('total_seats'), occupied=Sum('occupied_seats'))
            c_total_seats = seats['total'] or 0
            c_occupied = seats['occupied'] or 0
            institutions.append({
                'college': college,
                'total_applications': college_apps.count(),
                'admitted': college_apps.filter(status='Admitted').count(),
                'revenue': college_apps.filter(payment_status='Success').aggregate(
                    total=Sum('amount_paid'))['total'] or 0,
                'total_seats': c_total_seats,
                'occupied_seats': c_occupied,
                'utilization_pct': round((c_occupied / c_total_seats) * 100, 1) if c_total_seats else 0,
            })
        institutions.sort(key=lambda d: d['revenue'], reverse=True)
        max_institution_revenue = max((d['revenue'] for d in institutions), default=0) or 1
        for d in institutions:
            d['revenue_pct'] = round((d['revenue'] / max_institution_revenue) * 100, 1)

        # ---- Partner (CRE) leaderboard --------------------------------------
        referral_ay_filter = {f'referrals__{k}': v for k, v in ay_filter.items()}
        leaderboard = (
            CREProfile.objects.select_related('user')
            .annotate(
                successful_referrals=Count(
                    'referrals',
                    filter=Q(referrals__payment_status='Success', **referral_ay_filter)
                ),
                revenue_generated=Sum(
                    'referrals__amount_paid',
                    filter=Q(referrals__payment_status='Success', **referral_ay_filter)
                ),
            )
            .filter(successful_referrals__gt=0)
            .order_by('-revenue_generated')[:8]
        )

        # ---- Admission funnel -------------------------------------------------
        payment_success_count = apps_qs.filter(payment_status='Success').count()
        funnel_stage_colors = ['#86b6ef', '#2a78d6', '#184f95']
        funnel_raw = [
            ('Applied', total_applications),
            ('Payment Verified', payment_success_count),
            ('Admitted', total_admitted),
        ]
        funnel_max = funnel_raw[0][1] or 1
        funnel = [
            {
                'label': label, 'value': value,
                'pct': round((value / funnel_max) * 100, 1),
                'color': funnel_stage_colors[i],
            }
            for i, (label, value) in enumerate(funnel_raw)
        ]
        funnel_labels = [f['label'] for f in funnel]
        funnel_values = [f['value'] for f in funnel]

        leaderboard_list = list(leaderboard)
        max_leaderboard_revenue = max((float(cre.revenue_generated or 0) for cre in leaderboard_list), default=0) or 1
        for rank, cre in enumerate(leaderboard_list, start=1):
            cre.rank = rank
            cre.revenue_value = float(cre.revenue_generated or 0)
            cre.revenue_pct = round((cre.revenue_value / max_leaderboard_revenue) * 100, 1)
        leaderboard_names = [cre.user.username for cre in leaderboard_list]
        leaderboard_revenue = [cre.revenue_value for cre in leaderboard_list]
        leaderboard_referrals = [cre.successful_referrals for cre in leaderboard_list]

        # ---- Live activity feed -------------------------------------------
        # Merges three real, timestamped event sources network-wide
        # (nothing fabricated) and shows the most recent across all of them.
        # bg/fg are precomputed here (rather than branching in the template)
        # so the template only ever writes one unconditional style value.
        tone_styles = {
            'good': ('rgba(12,163,12,0.14)', '#0ca30c'),
            'serious': ('rgba(236,131,90,0.14)', '#ec835a'),
            'info': ('rgba(57,135,229,0.14)', '#3987e5'),
        }

        def _activity_item(at, icon, tone, text, by):
            bg, fg = tone_styles[tone]
            return {'at': at, 'icon': icon, 'text': text, 'by': by, 'bg': bg, 'fg': fg}

        activity = []
        for app in (Application.objects.filter(status='Admitted', admitted_at__isnull=False)
                    .select_related('student', 'college', 'closed_by').order_by('-admitted_at')[:6]):
            activity.append(_activity_item(
                app.admitted_at, 'user-check', 'good',
                f"{app.student.name} admitted to {app.college.name}",
                app.closed_by.username if app.closed_by else None,
            ))
        for app in (Application.objects.filter(commission_reviewed_at__isnull=False)
                    .select_related('student', 'commission_reviewed_by').order_by('-commission_reviewed_at')[:6]):
            approved = app.commission_status == 'Approved'
            activity.append(_activity_item(
                app.commission_reviewed_at,
                'badge-check' if approved else 'badge-x',
                'good' if approved else 'serious',
                (f"Commission approved for {app.student.name} (₹{app.commission_amount})" if approved
                 else f"Commission rejected for {app.student.name}"),
                app.commission_reviewed_by.username if app.commission_reviewed_by else None,
            ))
        for cre in CREProfile.objects.select_related('user').order_by('-user__date_joined')[:6]:
            activity.append(_activity_item(
                cre.user.date_joined, 'user-plus', 'info',
                f"{cre.user.username} joined the partner network",
                None,
            ))
        activity.sort(key=lambda a: a['at'], reverse=True)
        activity = activity[:10]

        context.update({
            'is_dashboard': True,
            'is_executive': True,
            'total_students': total_students,
            'total_applications': total_applications,
            'total_admitted': total_admitted,
            'total_removed': total_removed,
            'verified_revenue': verified_revenue,
            'approved_commission_payout': approved_commission_payout,
            'pending_commission_count': pending_commission_count,
            'awaiting_executive_commission_count': awaiting_executive_commission_count,
            'pending_verification_count': pending_verification_count,
            'total_colleges': total_colleges,
            'total_partners': total_partners,
            'pending_partner_approvals': pending_partner_approvals,
            'attention_count': attention_count,
            'total_seats': total_seats,
            'occupied_seats': occupied_seats,
            'seat_utilization_pct': seat_utilization_pct,
            'trend_labels': trend_labels,
            'trend_applications': trend_applications,
            'trend_revenue': trend_revenue,
            'trend_admitted': trend_admitted,
            'payment_breakdown': payment_breakdown,
            'institutions': institutions,
            'leaderboard': leaderboard_list,
            'leaderboard_names': leaderboard_names,
            'leaderboard_revenue': leaderboard_revenue,
            'leaderboard_referrals': leaderboard_referrals,
            'funnel': funnel,
            'funnel_labels': funnel_labels,
            'funnel_values': funnel_values,
            'payment_success_count': payment_success_count,
            'activity': activity,
        })
        return context


class ExecutiveCommissionDashboardView(AcademicYearFilterMixin, ExecutiveRequiredMixin, TemplateView):
    """
    The Executive's Commission Desk: the final sign-off stage of the
    commission workflow. By the time an application lands here, Finance
    has already reviewed it and set the payout amount
    (commission_status == 'Finance Approved' - see
    Application.finance_approve_commission in models.py); nothing is
    payable until the Executive also signs off.

    Lists every CRE who currently has at least one application waiting
    at this stage - grouped by CRE, not a flat list of applications,
    since the Executive reviews a partner's whole outstanding book at
    once. Click into a CRE (see ExecutiveCommissionCREDetailView) for
    the itemised list to actually approve or reject.

    Deliberately not scoped by the globally-selected Academic Year (the
    mixin is only mixed in so the filter bar in base.html still renders
    correctly on this page) - a payout waiting on sign-off doesn't stop
    waiting just because a different year is selected elsewhere.
    """
    template_name = 'admission_system/executive_commission_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Annotate over the full (unfiltered) 'referrals' relation, with the
        # 'Finance Approved' condition applied inside each aggregate's own
        # filter= - not as an outer .filter(referrals__...) on the base
        # queryset beforehand. Pre-filtering the base queryset by the same
        # relation the aggregates also reference creates a second join,
        # which inflates Count/Sum beyond the correct per-CRE totals.
        # Matches the same pattern already used for the leaderboard above.
        awaiting_filter = Q(referrals__commission_status='Finance Approved')
        cre_rows = (
            CREProfile.objects.select_related('user')
            .annotate(
                awaiting_count=Count('referrals', filter=awaiting_filter, distinct=True),
                awaiting_total=Sum('referrals__commission_amount', filter=awaiting_filter),
                oldest_awaiting_at=Min('referrals__commission_reviewed_at', filter=awaiting_filter),
            )
            .filter(awaiting_count__gt=0)
            .order_by('oldest_awaiting_at')
        )

        pending_apps = Application.objects.filter(commission_status='Finance Approved')

        context.update({
            'cre_rows': cre_rows,
            'awaiting_cre_count': cre_rows.count(),
            'awaiting_app_count': pending_apps.count(),
            'awaiting_total_amount': pending_apps.aggregate(total=Sum('commission_amount'))['total'] or 0,
            'is_dashboard': True,
            'is_executive': True,
        })
        return context


class ExecutiveCommissionCREDetailView(AcademicYearFilterMixin, ExecutiveRequiredMixin, TemplateView):
    """
    Drill-down from ExecutiveCommissionDashboardView: every commission
    application from one specific CRE, split into the ones awaiting the
    Executive's final sign-off (commission_status == 'Finance Approved'
    - actionable, with Approve/Reject buttons) and that CRE's own past
    commission history (Approved/Settled/Rejected - read-only context;
    'Approved' here just means the Finance Manager hasn't uploaded the
    payment receipt and settled it yet - see
    Application.settle_commission in models.py).

    Deliberately not scoped by the globally-selected Academic Year, for
    the same reason as ExecutiveCommissionDashboardView above.
    """
    template_name = 'admission_system/executive_commission_cre_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cre_profile = get_object_or_404(CREProfile.objects.select_related('user'), id=kwargs.get('cre_id'))

        awaiting_apps = Application.objects.filter(
            referred_by=cre_profile, commission_status='Finance Approved'
        ).select_related('student', 'college', 'course', 'commission_reviewed_by').order_by('commission_reviewed_at')

        history_apps = Application.objects.filter(
            referred_by=cre_profile, commission_status__in=['Approved', 'Settled', 'Rejected']
        ).select_related(
            'student', 'college', 'course', 'commission_reviewed_by', 'commission_executive_reviewed_by',
            'commission_settled_by',
        ).order_by('-commission_reviewed_at')[:25]

        context.update({
            'cre_profile': cre_profile,
            'awaiting_apps': awaiting_apps,
            'awaiting_total': awaiting_apps.aggregate(total=Sum('commission_amount'))['total'] or 0,
            'history_apps': history_apps,
            'is_dashboard': True,
            'is_executive': True,
        })
        return context


class ExecutiveCommissionActionView(ExecutiveRequiredMixin, View):
    """
    Handles the Approve/Reject buttons on the Executive's Commission
    Desk (CRE detail page). Delegates to
    Application.executive_approve_commission() /
    executive_reject_commission() (models.py), which only act on
    applications still at the 'Finance Approved' stage, so a double
    click or a stale page can't double-process one. Always redirects
    back to the CRE detail page the action was taken from.
    """
    def post(self, request, *args, **kwargs):
        application = get_object_or_404(
            Application.objects.select_related('student', 'referred_by'), id=kwargs.get('app_id')
        )
        action = request.POST.get('action')

        if application.commission_status != 'Finance Approved':
            messages.info(request, f"The commission application for {application.student.name} has already moved on.")
        elif action == 'approve':
            application.executive_approve_commission(user=request.user)
            messages.success(request, f"Final approval given for {application.student.name}'s ₹{application.commission_amount} commission.")
        elif action == 'reject':
            application.executive_reject_commission(user=request.user)
            messages.warning(request, f"Commission rejected for {application.student.name}.")

        return redirect('executive_commission_cre_detail', cre_id=application.referred_by_id)


from .forms import StudentAdmissionForm
from .models import FinanceProfile

def apply_admission(request, college_slug, username, cre_id):
    college = get_object_or_404(College, slug=college_slug)
    # username is validated against the CRE's actual account here so a
    # mismatched/stale username in the URL doesn't silently attribute the
    # referral to the wrong CRE.
    referrer = get_object_or_404(CREProfile, cre_id=cre_id, user__username=username)

    # If this CRE has since been deallocated from this college, the referral
    # link is dead. Checked live against allocated_colleges (not a separate
    # blacklist), so re-allocating the college instantly revives the link.
    # Superuser CRE profiles (auto-created for dashboard testing) are exempt
    # since they aren't given real per-college allocations.
    if not referrer.user.is_superuser and not referrer.allocated_colleges.filter(pk=college.pk).exists():
        raise Http404("This referral link is no longer active.")

    # Retrieve pending data from session
    pending_student_data = request.session.get('pending_student_data')
    has_files_in_session = bool(request.session.get('pending_files'))

    if request.method == 'POST':
        form = StudentAdmissionForm(request.POST, request.FILES, college=college, has_files_in_session=has_files_in_session)
        if form.is_valid():
            # Save student data to session
            student_data = {
                'email': form.cleaned_data['email'],
                'dob': form.cleaned_data['dob'].isoformat() if form.cleaned_data['dob'] else None,
                'gender': form.cleaned_data['gender'],
                'aadhar_number': form.cleaned_data['aadhar_number'],
                'blood_group': form.cleaned_data['blood_group'],
                'category': form.cleaned_data['category'],
                'permanent_address': form.cleaned_data['permanent_address'],
                'correspondence_address': form.cleaned_data['correspondence_address'],
                'state': form.cleaned_data['state'],
                'city': form.cleaned_data['city'],
                'father_name': form.cleaned_data['father_name'],
                'father_mobile': form.cleaned_data['father_mobile'],
                'father_occupation': form.cleaned_data['father_occupation'],
                'mother_name': form.cleaned_data['mother_name'],
                'mother_mobile': form.cleaned_data['mother_mobile'],
                'mother_occupation': form.cleaned_data['mother_occupation'],
                'guardian_name': form.cleaned_data['guardian_name'],
                'guardian_mobile': form.cleaned_data['guardian_mobile'],
                'preferred_contact': form.cleaned_data['preferred_contact'],
                'name': form.cleaned_data['name'],
                'phone': form.cleaned_data['phone'],
            }
            
            # Check for existing application before proceeding
            student = Student.objects.filter(email=student_data['email']).first()
            if not student:
                student = Student.objects.filter(phone=student_data['phone']).first()
                
            if student:
                course = form.cleaned_data['course']
                existing_app = Application.objects.filter(student=student, college=college, course=course).first()
                if existing_app:
                    if existing_app.payment_status == 'Success':
                        messages.success(request, f"You have already successfully applied for {course.name} at {college.name}.")
                        return redirect('apply_admission', college_slug=college.slug, username=username, cre_id=cre_id)
                    elif existing_app.payment_status == 'Pending Verification':
                        if existing_app.referred_by and existing_app.referred_by.cre_id != referrer.cre_id:
                            messages.error(request, f"This student is already registered through another partner for {course.name}. Duplicate registrations across different partners are not allowed.")
                            return redirect('apply_admission', college_slug=college.slug, username=username, cre_id=cre_id)
                        messages.warning(request, "Your previous payment for this course is currently being verified. Please do not pay again.")
                        return redirect('apply_admission', college_slug=college.slug, username=username, cre_id=cre_id)

                    if existing_app.referred_by and existing_app.referred_by.cre_id != referrer.cre_id:
                        messages.error(request, f"This student was previously registered through another partner. Please contact the administrator for cross-partner transfers.")
                        return redirect('apply_admission', college_slug=college.slug, username=username, cre_id=cre_id)

            # Save application data to session
            course = form.cleaned_data['course']
            source = form.cleaned_data.get('source', '')
            
            application_data = {
                'college': college.id,
                'course': course.id,
                'addon_course': form.cleaned_data['addon_course'],
                'source': source,
                'referred_by': referrer.id,
            }
            
            # Handle file uploads (save temporarily to default storage, keep path in session)
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            import os
            
            file_paths = request.session.get('pending_files', {})
            
            for doc_field in ['doc_10th', 'doc_11th', 'doc_12th', 'doc_aadhar', 'photo']:
                uploaded_file = form.cleaned_data.get(doc_field)
                if uploaded_file:
                    # Clean up old file if replacing
                    if doc_field in file_paths and default_storage.exists(file_paths[doc_field]):
                        default_storage.delete(file_paths[doc_field])

                    file_name = default_storage.save(f"temp/{uploaded_file.name}", ContentFile(uploaded_file.read()))
                    file_paths[doc_field] = file_name

            request.session['pending_student_data'] = student_data
            request.session['pending_application_data'] = application_data
            request.session['pending_files'] = file_paths
            request.session['pending_college_slug'] = college_slug
            request.session['pending_username'] = username
            request.session['pending_cre_id'] = str(cre_id)
            
            return redirect('manual_payment')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        # Pre-fill form if session data exists
        initial_data = {}
        if pending_student_data:
            initial_data.update(pending_student_data)
        
        pending_app_data = request.session.get('pending_application_data')
        if pending_app_data:
            initial_data['course'] = pending_app_data.get('course')
            initial_data['addon_course'] = pending_app_data.get('addon_course')
            initial_data['source'] = pending_app_data.get('source')
            
        form = StudentAdmissionForm(college=college, initial=initial_data, has_files_in_session=has_files_in_session)

    courses = college.courses.all()
    
    template_slug = college.slug.lower()
    if template_slug == 'jbc':
        template_slug = 'jbcmet'
        
    template_name = f'admission_system/college_{template_slug}.html'
    try:
        from django.template.loader import get_template
        get_template(template_name)
    except:
        template_name = 'admission_system/college_static.html'

    return render(request, template_name, {
        'college': college,
        'courses': courses,
        'username': username,
        'cre_id': cre_id,
        'form': form
    })

from django.db import transaction

def manual_payment(request):
    pending_student_data = request.session.get('pending_student_data')
    pending_application_data = request.session.get('pending_application_data')
    pending_files = request.session.get('pending_files', {})
    college_slug = request.session.get('pending_college_slug')
    username = request.session.get('pending_username')
    cre_id = request.session.get('pending_cre_id')

    if not all([pending_student_data, pending_application_data, college_slug, username, cre_id]):
        messages.error(request, "No pending application found. Please fill out the admission form first.")
        return redirect('home')

    college = get_object_or_404(College, slug=college_slug)
    course = get_object_or_404(Course, id=pending_application_data['course'])

    if request.method == "POST":
        transaction_id = request.POST.get('transaction_id')
        payment_screenshot = request.FILES.get('payment_screenshot')
        
        if transaction_id and payment_screenshot:
            if Application.objects.filter(transaction_id=transaction_id).exists():
                messages.error(request, "This Transaction ID has already been used. Please provide the unique ID for this payment.")
                return render(request, 'admission_system/manual_payment.html', {
                    'college': college,
                    'course': course,
                    'college_slug': college_slug,
                    'username': username,
                    'cre_id': cre_id,
                    'upi_id': college.upi_id or settings.UPI_ID,
                    'upi_payee_name': college.upi_payee_name or settings.UPI_PAYEE_NAME
                })

            try:
                with transaction.atomic():
                    # 1. Save/Update Student
                    email = pending_student_data['email']
                    student, created = Student.objects.update_or_create(
                        email=email,
                        defaults={
                            'name': pending_student_data['name'],
                            'phone': pending_student_data['phone'],
                            'dob': pending_student_data.get('dob') if pending_student_data.get('dob') else None,
                            'gender': pending_student_data.get('gender'),
                            'aadhar_number': pending_student_data.get('aadhar_number'),
                            'blood_group': pending_student_data.get('blood_group'),
                            'category': pending_student_data.get('category'),
                            'permanent_address': pending_student_data.get('permanent_address'),
                            'correspondence_address': pending_student_data.get('correspondence_address'),
                            'state': pending_student_data.get('state'),
                            'city': pending_student_data.get('city'),
                            'father_name': pending_student_data.get('father_name'),
                            'father_mobile': pending_student_data.get('father_mobile'),
                            'father_occupation': pending_student_data.get('father_occupation'),
                            'mother_name': pending_student_data.get('mother_name'),
                            'mother_mobile': pending_student_data.get('mother_mobile'),
                            'mother_occupation': pending_student_data.get('mother_occupation'),
                            'guardian_name': pending_student_data.get('guardian_name'),
                            'guardian_mobile': pending_student_data.get('guardian_mobile'),
                            'preferred_contact': pending_student_data.get('preferred_contact'),
                        }
                    )

                    # 1b. Attach the passport-size photo to the Student record
                    # (not Application - it's a student identity attribute).
                    # Staged earlier in apply_admission() the same way the
                    # 10th/11th/12th/Aadhar docs are, as a temp file in
                    # default_storage, keyed by field name in pending_files.
                    from django.core.files.storage import default_storage as _default_storage
                    from django.core.files import File as _File
                    import os as _os
                    photo_path = pending_files.get('photo')
                    if photo_path and _default_storage.exists(photo_path):
                        with _default_storage.open(photo_path) as f:
                            student.photo.save(_os.path.basename(photo_path), _File(f))
                        _default_storage.delete(photo_path)
                        student.save()

                    # 2. Check for duplicate successful application just in case
                    if Application.objects.filter(student=student, college=college, course=course, payment_status='Success').exists():
                        messages.error(request, f"You have already successfully applied for {course.name} at {college.name}.")
                        return redirect('apply_admission', college_slug=college_slug, username=username, cre_id=cre_id)

                    # 3. Resolve ForeignKey objects
                    referrer = None
                    cre_profile_id = pending_application_data.get('referred_by')
                    if cre_profile_id:
                        referrer = get_object_or_404(CREProfile, id=cre_profile_id)

                        # Second checkpoint: the CRE may have been deallocated
                        # from this college after the student filled the form
                        # but before paying. Block the save rather than let a
                        # dead link's submission slip through at the last step.
                        if not referrer.user.is_superuser and not referrer.allocated_colleges.filter(pk=college.pk).exists():
                            for key in ['pending_student_data', 'pending_application_data', 'pending_files', 'pending_college_slug', 'pending_username', 'pending_cre_id']:
                                if key in request.session:
                                    del request.session[key]
                            messages.error(request, "This referral link is no longer active. Please contact the institution directly.")
                            return redirect('home')

                    source = pending_application_data.get('source')

                    # 4. Save/Update Application
                    app, _ = Application.objects.update_or_create(
                        student=student, college=college, course=course,
                        defaults={
                            'addon_course': pending_application_data.get('addon_course'),
                            'source': source,
                            'referred_by': referrer,
                            'payment_status': 'Pending Verification',
                            'transaction_id': transaction_id,
                            'payment_screenshot': payment_screenshot,
                        }
                    )
                    
                    # Process files from default_storage
                    from django.core.files.storage import default_storage
                    from django.core.files import File
                    import os
                    for doc_field in ['doc_10th', 'doc_11th', 'doc_12th', 'doc_aadhar']:
                        file_path = pending_files.get(doc_field)
                        if file_path and default_storage.exists(file_path):
                            with default_storage.open(file_path) as f:
                                getattr(app, doc_field).save(os.path.basename(file_path), File(f))
                            default_storage.delete(file_path)
                    
                    app.save()

                # Clear pending data from session on success
                for key in ['pending_student_data', 'pending_application_data', 'pending_files', 'pending_college_slug', 'pending_username', 'pending_cre_id']:
                    if key in request.session:
                        del request.session[key]

                return render(request, 'admission_system/success.html', {'college': college, 'app': app, 'username': username, 'cre_id': cre_id})

            except Exception as e:
                messages.error(request, f"An error occurred while saving your application: {e}")
                return render(request, 'admission_system/manual_payment.html', {
                    'college': college,
                    'course': course,
                    'college_slug': college_slug,
                    'username': username,
                    'cre_id': cre_id,
                    'upi_id': college.upi_id or settings.UPI_ID,
                    'upi_payee_name': college.upi_payee_name or settings.UPI_PAYEE_NAME
                })
        else:
            messages.error(request, "Please provide both Transaction ID and the Payment Screenshot.")

    return render(request, 'admission_system/manual_payment.html', {
        'college': college,
        'course': course,
        'college_slug': college_slug,
        'username': username,
        'cre_id': cre_id,
        'upi_id': college.upi_id or settings.UPI_ID,
        'upi_payee_name': college.upi_payee_name or settings.UPI_PAYEE_NAME
    })

def home(request):
    if request.user.is_authenticated and hasattr(request.user, 'cre_profile'):
        return redirect('cre_dashboard')
    return render(request, 'admission_system/home.html')


def check_username(request):
    """API endpoint for live username-availability checking on the CRE
    registration form. Called as the user types/leaves the username
    field, so a duplicate is caught right away instead of only after
    the whole form is submitted. If the username is taken, a free
    alternative is suggested using a regex-based numeric-suffix scheme
    (see utils.suggest_unique_username)."""
    username = request.GET.get('username', '').strip()

    if not username:
        return JsonResponse({'available': None})

    if is_username_taken(username):
        suggestion = suggest_unique_username(username)
        message = f"'{username}' is already taken."
        if suggestion:
            message += f" Try '{suggestion}'."
        return JsonResponse({
            'available': False,
            'suggestion': suggestion,
            'message': message,
        })

    return JsonResponse({'available': True, 'message': f"'{username}' is available."})


def check_duplicate_application(request):
    """API endpoint to check if a student with the given aadhar number
    has already applied for the same course at the same college."""
    aadhar_number = request.GET.get('aadhar_number', '').strip()
    course_id = request.GET.get('course_id', '').strip()
    college_slug = request.GET.get('college_slug', '').strip()

    if not aadhar_number or not course_id or not college_slug:
        return JsonResponse({'exists': False})

    try:
        college = College.objects.get(slug=college_slug)
    except College.DoesNotExist:
        return JsonResponse({'exists': False})

    existing = Application.objects.filter(
        student__aadhar_number=aadhar_number,
        course_id=course_id,
        college=college,
    ).select_related('student', 'course').first()

    if existing:
        return JsonResponse({
            'exists': True,
            'student_name': existing.student.name,
            'course_name': existing.course.name,
            'payment_status': existing.payment_status,
            'message': f"A student with this Aadhar number has already applied for {existing.course.name} at {college.name}. (Status: {existing.payment_status})"
        })

    return JsonResponse({'exists': False})

def _pdf_link_callback(uri, rel):
    """
    xhtml2pdf's link_callback: resolves an <img src="..."> URI to something
    it can actually read.

    - An absolute http(s) URL (the student's photo when stored on S3, where
      Student.photo.url returns a full, signed S3 URL) is passed through
      unchanged - xhtml2pdf fetches it over the network itself.
    - A local MEDIA_URL-relative path (photo stored on local FileSystemStorage
      in dev, where .url() returns e.g. "/media/student_photos/x.jpg") is
      resolved to an absolute filesystem path under MEDIA_ROOT, since
      xhtml2pdf can't resolve a site-relative URL on its own.
    """
    if uri.startswith('http://') or uri.startswith('https://'):
        return uri

    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, '', 1))
    elif uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, '', 1))
    else:
        return uri

    return path


def download_application_pdf(request, app_id):
    app = get_object_or_404(Application, id=app_id)
    template_path = 'admission_system/pdf_template.html'
    context = {'app': app}

    # Create a Django response object, and specify content_type as pdf
    response = HttpResponse(content_type='application/pdf')
    # if you want to download it, uncomment below
    response['Content-Disposition'] = f'attachment; filename="Application_Form_{app.student.name.replace(" ", "_")}.pdf"'

    # find the template and render it.
    template = get_template(template_path)
    html = template.render(context)

    # create a pdf
    from xhtml2pdf import pisa
    pisa_status = pisa.CreatePDF(
       html, dest=response, link_callback=_pdf_link_callback)

    # if error then show some funny view
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response
