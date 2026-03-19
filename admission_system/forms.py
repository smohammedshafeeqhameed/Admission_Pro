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

class StudentAdmissionForm(forms.Form):
    name = forms.CharField(max_length=255, required=True, label="Full Name")
    email = forms.EmailField(required=True, label="Email Address")
    phone = forms.CharField(
        max_length=15, 
        required=True, 
        label="Phone Number",
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', "Enter a valid phone number. E.g. +91 9999999999")]
    )
    course = forms.ModelChoiceField(queryset=Course.objects.none(), required=True, label="Course Selection")

    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        if college:
            self.fields['course'].queryset = college.courses.all()

class AdmissionForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['course']
