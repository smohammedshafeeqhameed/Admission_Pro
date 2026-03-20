from django.db import models
from django.contrib.auth.models import User
import uuid

class College(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    website_content = models.TextField(help_text="HTML content for the college static page")
    theme_color = models.CharField(max_length=7, default="#6366f1", help_text="HEX color code for institutional branding")
    logo_url = models.URLField(blank=True, null=True, help_text="URL to the institution's logo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Course(models.Model):
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=255)
    description = models.TextField()

    class Meta:
        unique_together = ('college', 'name')

    def __str__(self):
        return f"{self.name} - {self.college.name}"

class CREProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cre_profile')
    cre_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    phone = models.CharField(max_length=15, blank=True)
    is_approved = models.BooleanField(default=False, help_text="Admin approval status for dashboard access")
    allocated_colleges = models.ManyToManyField(College, blank=True, related_name='assigned_cres')
    
    def __str__(self):
        return f"CRE: {self.user.username}"

class Student(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female'), ('O', 'Other')]
    BLOOD_GROUP_CHOICES = [('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'), ('O+', 'O+'), ('O-', 'O-'), ('AB+', 'AB+'), ('AB-', 'AB-')]
    
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

    def __str__(self):
        return self.name

from django.core.exceptions import ValidationError

class Application(models.Model):
    PAYMENT_STATUS_CHOICES = [('Pending', 'Pending'), ('Success', 'Success'), ('Failed', 'Failed')]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='applications')
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='applications')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='applications')
    addon_course = models.CharField(max_length=255, blank=True, null=True)
    referred_by = models.ForeignKey(CREProfile, on_delete=models.SET_NULL, null=True, related_name='referrals')
    applied_at = models.DateTimeField(auto_now_add=True)
    
    # Documents
    doc_10th = models.FileField(upload_to='documents/10th/', null=True, blank=True)
    doc_11th = models.FileField(upload_to='documents/11th/', null=True, blank=True)
    doc_12th = models.FileField(upload_to='documents/12th/', null=True, blank=True)
    doc_aadhar = models.FileField(upload_to='documents/aadhar/', null=True, blank=True)
    
    # Payment
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

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
