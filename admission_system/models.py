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
    allocated_colleges = models.ManyToManyField(College, blank=True, related_name='assigned_cres')
    
    def __str__(self):
        return f"CRE: {self.user.username}"

class Student(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    
    def __str__(self):
        return self.name

from django.core.exceptions import ValidationError

class Application(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='applications')
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='applications')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='applications')
    referred_by = models.ForeignKey(CREProfile, on_delete=models.SET_NULL, null=True, related_name='referrals')
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'college', 'course')

    def clean(self):
        # 1. Ensure the course belongs to the selected college
        if self.course and self.college and self.course.college != self.college:
            raise ValidationError({
                'course': f"The selected course '{self.course.name}' does not belong to '{self.college.name}'."
            })
        
        # 2. Duplicate Check for better Admin feedback
        if not self.pk:  # Only for new records
            if Application.objects.filter(student=self.student, college=self.college, course=self.course).exists():
                raise ValidationError("This student has already applied for this course at this college.")

    def __str__(self):
        return f"{self.student.name} -> {self.college.name} ({self.course.name})"
