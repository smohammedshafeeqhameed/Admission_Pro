from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count, Sum
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
from django.http import HttpResponse
import boto3
from django.conf import settings
from django.utils.text import slugify
from django.http import JsonResponse
from .models import AddonCourse, CampusManagerProfile
from django.template.loader import get_template


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

class AdminDashboardView(SuperuserRequiredMixin, TemplateView):
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
        
        context.update({
            'total_students': Student.objects.count(),
            'total_cres': CREProfile.objects.count(),
            'total_colleges': College.objects.count(),
            'total_applications': Application.objects.count(),
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

class AdminCREDetailView(SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_cre_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cre_id = self.kwargs.get('pk')
        cre_profile = None
        if cre_id:
            cre_profile = get_object_or_404(CREProfile, id=cre_id)
        
        # All referrals (students applied through this CRE)
        referrals = Application.objects.filter(referred_by=cre_profile).select_related('student', 'college', 'course').order_by('-applied_at')
        
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

class AdminCollegeListView(SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_college_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        colleges = College.objects.annotate(
            student_count=Count('applications', distinct=True),
            course_count=Count('courses', distinct=True)
        )
        context['colleges'] = colleges
        context['is_dashboard'] = True
        return context

class AdminCollegeDetailView(SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_college_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        college_id = self.kwargs.get('pk')
        college = get_object_or_404(College, id=college_id)
        courses = college.courses.all().annotate(
            applicant_count=Count('applications')
        )
        
        context.update({
            'college': college,
            'courses': courses,
            'total_students': Application.objects.filter(college=college).count(),
            'is_dashboard': True
        })
        return context

class AdminCourseStudentListView(SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_course_student_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        applications = Application.objects.filter(course=course).select_related('student', 'college', 'referred_by__user').order_by('-applied_at')
        
        context.update({
            'course': course,
            'college': course.college,
            'applications': applications,
            'total_enrollments': applications.count(),
            'successful_enrollments': applications.filter(payment_status='Success').count(),
            'pending_enrollments': applications.filter(payment_status='Pending').count(),
            'is_dashboard': True
        })
        return context

class AdminStudentDetailView(SuperuserRequiredMixin, TemplateView):
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

class FinanceRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or hasattr(self.request.user, 'finance_profile')

class FinanceDashboardView(FinanceRequiredMixin, TemplateView):
    template_name = 'admission_system/finance_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        college_id = self.request.GET.get('college')
        
        # Use a base queryset with select_related to avoid additional student/college/course lookups
        base_apps = Application.objects.select_related('student', 'college', 'course')
        
        # Pending verifications - prioritize these
        pending_apps = base_apps.filter(payment_status='Pending Verification')
        
        # History - limit to last 50 for performance
        history_apps = base_apps.exclude(payment_status__in=['Pending', 'Pending Verification']).order_by('-applied_at')
        
        if college_id:
            pending_apps = pending_apps.filter(college_id=college_id)
            history_apps = history_apps.filter(college_id=college_id)
            context['active_college'] = get_object_or_404(College, id=college_id)
            
        # Global Stats - Single aggregate query
        stats = Application.objects.filter(payment_status='Success').aggregate(
            total_revenue=Sum('amount_paid'),
            total_verified=Count('id')
        )
        total_revenue = stats['total_revenue'] or 0
        total_verified = stats['total_verified'] or 0
        
        # College Breakdown - Optimized with conditional annotation to replace N+1 loop
        colleges_with_stats = College.objects.annotate(
            revenue=Sum('applications__amount_paid', filter=Q(applications__payment_status='Success')),
            app_count=Count('applications', filter=Q(applications__payment_status='Success'))
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

class CampusManagerDashboardView(CampusManagerRequiredMixin, TemplateView):
    template_name = 'admission_system/campus_manager_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manager_profile = self.request.user.campus_manager_profile
        college = manager_profile.college
        
        # Base Querysets for this campus
        campus_apps = Application.objects.filter(college=college).select_related('student', 'course', 'referred_by')
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

class CampusManagerExportCSVView(CampusManagerRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        manager_profile = request.user.campus_manager_profile
        college = manager_profile.college
        course_id = request.GET.get('course_id')
        
        apps = Application.objects.filter(college=college).select_related('student', 'course', 'referred_by__user')
        
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
            'Name', 'Email', 'DOB', 'Gender', 'Aadhar Number', 'Blood Group',
            'Category', 'City', 'State', 'Father Name', 'Father Mobile', 
            'Course', 'Addon Course', 'Referred By', 'Reference', 'Payment Status', 'Applied Date'
        ])
        
        for app in apps:
            writer.writerow([
                app.student.name, 
                app.student.email, 
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

class AdminExportCSVView(SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        export_type = request.GET.get('type', 'students')
        course_id = request.GET.get('course_id')
        
        if export_type == 'students':
            apps = Application.objects.select_related('student', 'college', 'course', 'referred_by__user').all()
            
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
                'Name', 'Email', 'DOB', 'Gender', 'Aadhar Number', 'Blood Group',
                'Category', 'City', 'State', 'Father Name', 'Father Mobile', 'Applied College', 
                'Applied Course', 'Addon Course', 'Referred By', 'Reference', 'Payment Status', 'Applied Date'
            ])
            
            for app in apps:
                writer.writerow([
                    app.student.name, 
                    app.student.email, 
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
        
        # Check if it's a CRE and if they are approved
        cre_profile = getattr(user, 'cre_profile', None)
        if cre_profile and not cre_profile.is_approved and not user.is_superuser:
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
        if self.request.user.is_superuser:
            return reverse_lazy('admin_dashboard')
        if hasattr(self.request.user, 'finance_profile'):
            return reverse_lazy('finance_dashboard')
        if hasattr(self.request.user, 'campus_manager_profile'):
            return reverse_lazy('campus_manager_dashboard')
        return reverse_lazy('cre_dashboard')

class DashboardView(LoginRequiredMixin, TemplateView):
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
            
        referrals = Application.objects.filter(referred_by=cre_profile).order_by('-applied_at')
        
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
            if hasattr(request.user, 'finance_profile'):
                return redirect('finance_dashboard')
            
            if hasattr(request.user, 'campus_manager_profile'):
                return redirect('campus_manager_dashboard')
            
            cre_profile = getattr(request.user, 'cre_profile', None)
            if cre_profile and not cre_profile.is_approved and not request.user.is_superuser:
                from django.contrib.auth import logout
                logout(request)
                messages.error(request, "Your account is pending approval. Please contact the administrator.")
                return redirect('login')
                
            if not cre_profile and not request.user.is_superuser:
                messages.error(request, "This account is not registered as a CRE.")
                return render(request, 'admission_system/home.html', {'error': True})
                
        return super().dispatch(request, *args, **kwargs)

from .forms import StudentAdmissionForm
from .models import FinanceProfile

def apply_admission(request, college_slug, cre_id):
    college = get_object_or_404(College, slug=college_slug)
    referrer = get_object_or_404(CREProfile, cre_id=cre_id)
    
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
                        return redirect('apply_admission', college_slug=college.slug, cre_id=cre_id)
                    elif existing_app.payment_status == 'Pending Verification':
                        if existing_app.referred_by and existing_app.referred_by.cre_id != referrer.cre_id:
                            messages.error(request, f"This student is already registered through another partner for {course.name}. Duplicate registrations across different partners are not allowed.")
                            return redirect('apply_admission', college_slug=college.slug, cre_id=cre_id)
                        messages.warning(request, "Your previous payment for this course is currently being verified. Please do not pay again.")
                        return redirect('apply_admission', college_slug=college.slug, cre_id=cre_id)
                    
                    if existing_app.referred_by and existing_app.referred_by.cre_id != referrer.cre_id:
                        messages.error(request, f"This student was previously registered through another partner. Please contact the administrator for cross-partner transfers.")
                        return redirect('apply_admission', college_slug=college.slug, cre_id=cre_id)

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
            
            for doc_field in ['doc_10th', 'doc_11th', 'doc_12th', 'doc_aadhar']:
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
        'cre_id': cre_id,
        'form': form
    })

from django.db import transaction

def manual_payment(request):
    pending_student_data = request.session.get('pending_student_data')
    pending_application_data = request.session.get('pending_application_data')
    pending_files = request.session.get('pending_files', {})
    college_slug = request.session.get('pending_college_slug')
    cre_id = request.session.get('pending_cre_id')

    if not all([pending_student_data, pending_application_data, college_slug, cre_id]):
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

                    # 2. Check for duplicate successful application just in case
                    if Application.objects.filter(student=student, college=college, course=course, payment_status='Success').exists():
                        messages.error(request, f"You have already successfully applied for {course.name} at {college.name}.")
                        return redirect('apply_admission', college_slug=college_slug, cre_id=cre_id)

                    # 3. Resolve ForeignKey objects
                    referrer = None
                    cre_profile_id = pending_application_data.get('referred_by')
                    if cre_profile_id:
                        referrer = get_object_or_404(CREProfile, id=cre_profile_id)
                        
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
                for key in ['pending_student_data', 'pending_application_data', 'pending_files', 'pending_college_slug', 'pending_cre_id']:
                    if key in request.session:
                        del request.session[key]

                return render(request, 'admission_system/success.html', {'college': college, 'app': app})

            except Exception as e:
                messages.error(request, f"An error occurred while saving your application: {e}")
                return render(request, 'admission_system/manual_payment.html', {
                    'college': college,
                    'course': course,
                    'college_slug': college_slug,
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
        'cre_id': cre_id,
        'upi_id': college.upi_id or settings.UPI_ID,
        'upi_payee_name': college.upi_payee_name or settings.UPI_PAYEE_NAME
    })

def home(request):
    if request.user.is_authenticated and hasattr(request.user, 'cre_profile'):
        return redirect('cre_dashboard')
    return render(request, 'admission_system/home.html')


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
       html, dest=response)
       
    # if error then show some funny view
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response
