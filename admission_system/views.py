from django.shortcuts import render, redirect, get_object_or_404
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

class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

class AdminDashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'total_students': Student.objects.count(),
            'total_cres': CREProfile.objects.count(),
            'total_colleges': College.objects.count(),
            'total_applications': Application.objects.count(),
            'all_cres': CREProfile.objects.select_related('user').prefetch_related('allocated_colleges').all(),
            'all_colleges': College.objects.all(),
            'recent_applications': Application.objects.select_related('student', 'college', 'course', 'referred_by__user').order_by('-applied_at')[:10],
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

class AdminExportCSVView(SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        export_type = request.GET.get('type', 'students')
        
        if export_type == 'students':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="students_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Name', 'Email', 'Phone', 'Applied College', 'Applied Course', 'Referred By'])
            
            apps = Application.objects.select_related('student', 'college', 'course', 'referred_by__user').all()
            for app in apps:
                writer.writerow([
                    app.student.name, 
                    app.student.email, 
                    app.student.phone, 
                    app.college.name, 
                    app.course.name, 
                    app.referred_by.user.username if app.referred_by else 'Direct'
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
        messages.success(self.request, "Account created successfully! You are now logged in.")
        login(self.request, user)
        return redirect(self.success_url)

class CRELoginView(LoginView):
    template_name = 'admission_system/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        remember_me = self.request.POST.get('remember_me')
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
            'is_cre': True
        })
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not hasattr(request.user, 'cre_profile') and not request.user.is_superuser:
            messages.error(request, "This account is not registered as a CRE.")
            # We render the home page logic here or redirect
            return render(request, 'admission_system/home.html', {'error': True})
        return super().dispatch(request, *args, **kwargs)

from .forms import StudentAdmissionForm

def apply_admission(request, college_slug, cre_id):
    college = get_object_or_404(College, slug=college_slug)
    referrer = get_object_or_404(CREProfile, cre_id=cre_id)
    
    if request.method == 'POST':
        form = StudentAdmissionForm(request.POST, college=college)
        if form.is_valid():
            student_name = form.cleaned_data['name']
            student_email = form.cleaned_data['email']
            student_phone = form.cleaned_data['phone']
            course = form.cleaned_data['course']
            
            # Get or create student
            student, created = Student.objects.get_or_create(
                email=student_email,
                defaults={'name': student_name, 'phone': student_phone}
            )
            
            # Validation: Check if student already applied for this course in this college
            if Application.objects.filter(student=student, college=college, course=course).exists():
                messages.error(request, f"You have already applied for {course.name} at {college.name}.")
            else:
                Application.objects.create(
                    student=student,
                    college=college,
                    course=course,
                    referred_by=referrer
                )
                messages.success(request, f"Your application for {course.name} at {college.name} has been submitted successfully!")
                return render(request, 'admission_system/success.html', {'college': college})
        else:
            # If form is invalid, display the first error message
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")

    courses = college.courses.all()
    return render(request, 'admission_system/college_static.html', {
        'college': college,
        'courses': courses,
        'cre_id': cre_id
    })

def home(request):
    if request.user.is_authenticated and hasattr(request.user, 'cre_profile'):
        return redirect('cre_dashboard')
    return render(request, 'admission_system/home.html')
