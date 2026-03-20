from django import forms
from django.contrib.auth.models import User
from .models import CREProfile, Application, Course

class CRERegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    phone = forms.CharField(max_length=15, required=False)

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match")
        return cleaned_data

import re
from django.core.validators import RegexValidator

from .models import CREProfile, Application, Course, Student

class StudentAdmissionForm(forms.ModelForm):
    # Additional fields from Application model or custom ones
    addon_course = forms.CharField(max_length=255, required=False, label="Add-on Course")
    course = forms.ModelChoiceField(queryset=Course.objects.none(), required=True, label="Main Course")
    
    # Documents (to be handled in Application model)
    doc_10th = forms.FileField(required=True, label="10th Marksheet")
    doc_11th = forms.FileField(required=False, label="11th Marksheet")
    doc_12th = forms.FileField(required=True, label="12th Marksheet")
    doc_aadhar = forms.FileField(required=True, label="Aadhar Card Copy")

    class Meta:
        model = Student
        fields = [
            'name', 'dob', 'gender', 'aadhar_number', 'phone', 'email',
            'blood_group', 'category', 'permanent_address', 'correspondence_address',
            'state', 'city', 'father_name', 'father_mobile', 'father_occupation',
            'mother_name', 'mother_mobile', 'mother_occupation',
            'guardian_name', 'guardian_mobile', 'preferred_contact'
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'permanent_address': forms.Textarea(attrs={'rows': 2}),
            'correspondence_address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        if college:
            self.fields['course'].queryset = college.courses.all()
        
        # Add Tailwind classes to all fields
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all font-medium placeholder-slate-400'
            })
