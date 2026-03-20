from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count
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
            
        context.update({
            'total_students': Student.objects.count(),
            'total_cres': CREProfile.objects.count(),
            'total_colleges': College.objects.count(),
            'total_applications': Application.objects.count(),
            'all_cres': cres.distinct(),
            'all_colleges': College.objects.all(),
            'search_query': search_query,
            'selected_college': int(college_id) if college_id and college_id.isdigit() else None
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
        cre_profile = get_object_or_404(CREProfile, id=cre_id)
        
        # All referrals (students applied through this CRE)
        referrals = Application.objects.filter(referred_by=cre_profile).select_related('student', 'college', 'course').order_by('-applied_at')
        
        context.update({
            'cre': cre_profile,
            'referrals': referrals,
            'total_referrals': referrals.count(),
            'successful_referrals': referrals.filter(payment_status='Success').count(),
            'pending_referrals': referrals.filter(payment_status='Pending').count(),
        })
        return context

class AdminCollegeListView(SuperuserRequiredMixin, TemplateView):
    template_name = 'admission_system/admin_college_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        colleges = College.objects.annotate(
            student_count=Count('applications', distinct=True),
            course_count=Count('courses', distinct=True)
        )
        context['colleges'] = colleges
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
        })
        return context

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
        if request.user.is_authenticated:
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

import razorpay
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

# Razorpay Client Initialization (Use settings for production)
RAZORPAY_KEY_ID = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_placeholder_id')
RAZORPAY_KEY_SECRET = getattr(settings, 'RAZORPAY_KEY_SECRET', 'placeholder_secret')
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def apply_admission(request, college_slug, cre_id):
    college = get_object_or_404(College, slug=college_slug)
    referrer = get_object_or_404(CREProfile, cre_id=cre_id)
    
    if request.method == 'POST':
        form = StudentAdmissionForm(request.POST, request.FILES, college=college)
        if form.is_valid():
            # 1. Save/Update Student
            email = form.cleaned_data['email']
            student, created = Student.objects.update_or_create(
                email=email,
                defaults={
                    'name': form.cleaned_data['name'],
                    'phone': form.cleaned_data['phone'],
                    'dob': form.cleaned_data['dob'],
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
                }
            )
            
            # 2. Check for existing successful application
            course = form.cleaned_data['course']
            existing_app = Application.objects.filter(student=student, college=college, course=course, payment_status='Success').exists()
            if existing_app:
                messages.error(request, f"You have already successfully applied for {course.name} at {college.name}.")
            else:
                # 3. Create/Update Pending Application
                app, _ = Application.objects.update_or_create(
                    student=student, college=college, course=course,
                    defaults={
                        'addon_course': form.cleaned_data['addon_course'],
                        'referred_by': referrer,
                        'doc_10th': form.cleaned_data['doc_10th'],
                        'doc_11th': form.cleaned_data['doc_11th'],
                        'doc_12th': form.cleaned_data['doc_12th'],
                        'doc_aadhar': form.cleaned_data['doc_aadhar'],
                        'payment_status': 'Pending'
                    }
                )
                
                # 4. Initialize Razorpay Order (1500 INR = 150000 Paise)
                amount = 1500 * 100 
                order_data = {
                    'amount': amount,
                    'currency': 'INR',
                    'receipt': f'receipt_app_{app.id}',
                    'payment_capture': 1
                }
                
                try:
                    razorpay_order = client.order.create(data=order_data)
                    app.razorpay_order_id = razorpay_order['id']
                    app.save()
                    
                    return render(request, 'admission_system/payment_gateway.html', {
                        'order_id': razorpay_order['id'],
                        'amount': amount,
                        'key_id': RAZORPAY_KEY_ID,
                        'student': student,
                        'college': college,
                        'app_id': app.id
                    })
                except Exception as e:
                    messages.error(request, f"Payment Gateway Error: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")

    courses = college.courses.all()
    template_name = f'admission_system/college_{college.slug}.html'
    try:
        from django.template.loader import get_template
        get_template(template_name)
    except:
        template_name = 'admission_system/college_static.html'

    return render(request, template_name, {
        'college': college,
        'courses': courses,
        'cre_id': cre_id,
        'form': StudentAdmissionForm(college=college)
    })

@csrf_exempt
def payment_callback(request):
    if request.method == "POST":
        try:
            payment_id = request.POST.get('razorpay_payment_id', '')
            order_id = request.POST.get('razorpay_order_id', '')
            signature = request.POST.get('razorpay_signature', '')
            
            params_dict = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            
            # Verify Signature
            client.utility.verify_payment_signature(params_dict)
            
            # Update Application
            app = Application.objects.get(razorpay_order_id=order_id)
            app.payment_status = 'Success'
            app.razorpay_payment_id = payment_id
            app.amount_paid = 1500.00
            app.save()
            
            return render(request, 'admission_system/success.html', {'college': app.college, 'app': app})
            
        except Exception as e:
            order_id = request.POST.get('razorpay_order_id', '')
            if order_id:
                app = Application.objects.filter(razorpay_order_id=order_id).first()
                if app:
                    app.payment_status = 'Failed'
                    app.save()
            return render(request, 'admission_system/payment_failed.html', {'error': str(e)})
    return redirect('home')

def home(request):
    if request.user.is_authenticated and hasattr(request.user, 'cre_profile'):
        return redirect('cre_dashboard')
    return render(request, 'admission_system/home.html')
