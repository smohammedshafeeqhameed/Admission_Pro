from django import forms
import datetime
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

from .models import CREProfile, Application, Course, Student, ApplicationSource

class StudentAdmissionForm(forms.ModelForm):
    # Additional fields from Application model or custom ones
    addon_course = forms.ChoiceField(choices=[('', 'Select Add-on Course')], required=False, label="Add-on Course")
    course = forms.ModelChoiceField(queryset=Course.objects.none(), required=True, label="Main Course")
    source = forms.CharField(required=True, label="Reference Source", widget=forms.TextInput(attrs={'placeholder': 'How did you hear about us?'}))
    
    # Documents (to be handled in Application model)
    doc_10th = forms.FileField(required=True, label="10th Marksheet")
    doc_11th = forms.FileField(required=False, label="11th Marksheet")
    doc_12th = forms.FileField(required=False, label="12th Marksheet")
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
        labels = {
            'father_name': '𝐅𝐚𝐭𝐡𝐞𝐫 𝐧𝐚𝐦𝐞:',
            'father_mobile': '𝐅𝐚𝐭𝐡𝐞𝐫 𝐦𝐨𝐛𝐢𝐥𝐞 𝐧𝐮𝐦𝐛𝐞𝐫 :',
            'father_occupation': '𝐅𝐚𝐭𝐡𝐞𝐫 𝐨𝐜𝐜𝐮𝐩𝐚𝐭𝐢𝐨𝐧:',
            'mother_name': '𝐌𝐨𝐭𝐡𝐞𝐫 𝐧𝐚𝐦𝐞 :',
            'mother_mobile': '𝐌𝐨𝐭𝐡𝐞𝐫 𝐦𝐨𝐛𝐢𝐥𝐞 𝐧𝐮𝐦𝐛𝐞𝐫 :',
            'mother_occupation': '𝐌𝐨𝐭𝐡𝐞𝐫 𝐨𝐜𝐜𝐮𝐩𝐚𝐭𝐢𝐨𝐧:',
            'guardian_name': '𝐆𝐚𝐫𝐝𝐢𝐚𝐧 𝐧𝐚𝐦𝐞:',
            'guardian_mobile': '𝐆𝐚𝐫𝐝𝐢𝐚𝐧 𝐦𝐨𝐛𝐢𝐥𝐞 𝐧𝐮𝐦𝐛𝐞𝐫 :',
            'preferred_contact': '𝐏𝐫𝐞𝐟𝐟𝐞𝐫𝐞𝐬 𝐜𝐨𝐧𝐭𝐚𝐜𝐭 :',
        }
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'email': forms.EmailInput(attrs={'placeholder': 'name@example.com'}),
            'permanent_address': forms.Textarea(attrs={'rows': 2}),
            'correspondence_address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        if college:
            self.fields['course'].queryset = college.courses.all()
            self.fields['course'].label_from_instance = lambda obj: f"{obj.name}"
        
        # Enforce mandatory selection for Gender, Blood Group, and Aadhar
        self.fields['gender'].required = True
        self.fields['blood_group'].required = True
        self.fields['aadhar_number'].required = True
        
        # If we have course data in POST, update addon_course choices to pass validation
        if 'course' in self.data:
            try:
                course_id = int(self.data.get('course'))
                from .models import AddonCourse
                addons = AddonCourse.objects.filter(course_id=course_id)
                self.fields['addon_course'].choices = [('', 'Select Add-on Course')] + [(a.name, a.name) for a in addons]
            except (ValueError, TypeError):
                pass
        elif self.initial.get('course'):
             # Handle initial data if any
             course = self.initial.get('course')
             from .models import AddonCourse
             addons = AddonCourse.objects.filter(course=course)
             self.fields['addon_course'].choices = [('', 'Select Add-on Course')] + [(a.name, a.name) for a in addons]
        
        # Add Tailwind classes to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all font-medium placeholder-slate-400'
            })
            if field.required:
                field.widget.attrs['required'] = 'required'

        # Set max date for DOB to prevent future dates and ensure minimum age (15 years)
        max_dob = datetime.date.today() - datetime.timedelta(days=15*365)
        self.fields['dob'].widget.attrs['max'] = max_dob.isoformat()

        # Custom placeholders for family profile
        custom_placeholders = {
            'father_name': '𝐅𝐚𝐭𝐡𝐞𝐫 𝐧𝐚𝐦𝐞:',
            'father_mobile': '𝐅𝐚𝐭𝐡𝐞𝐫 𝐦𝐨𝐛𝐢𝐥𝐞 𝐧𝐮𝐦𝐛𝐞𝐫 :',
            'father_occupation': '𝐅𝐚𝐭𝐡𝐞𝐫 𝐨𝐜𝐜𝐮𝐩𝐚𝐭𝐢𝐨𝐧:',
            'mother_name': '𝐌𝐨𝐭𝐡𝐞𝐫 𝐧𝐚𝐦𝐞 :',
            'mother_mobile': '𝐌𝐨𝐭𝐡𝐞𝐫 𝐦𝐨𝐛𝐢𝐥𝐞 𝐧𝐮𝐦𝐛𝐞𝐫 :',
            'mother_occupation': '𝐌𝐨𝐭𝐡𝐞𝐫 𝐨𝐜𝐜𝐮𝐩𝐚𝐭𝐢𝐨𝐧:',
            'guardian_name': '𝐆𝐚𝐫𝐝𝐢𝐚𝐧 𝐧𝐚𝐦𝐞:',
            'guardian_mobile': '𝐆𝐚𝐫𝐝𝐢𝐚𝐧 𝐦𝐨𝐛𝐢𝐥𝐞 𝐧𝐮𝐦𝐛𝐞𝐫 :',
            'preferred_contact': '𝐏𝐫𝐞𝐟𝐟𝐞𝐫𝐞𝐬 𝐜𝐨𝐧𝐭𝐚𝐜𝐭 :',
        }
        for field_name, placeholder_text in custom_placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['placeholder'] = placeholder_text
            
        # Specific frontend validations
        name_pattern = "^[A-Za-z\\s]+$"
        name_title = "Only letters and spaces are allowed"
        for field_name in ['name', 'father_name', 'mother_name', 'guardian_name']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'pattern': name_pattern,
                    'title': name_title,
                    'minlength': '3'
                })

        phone_pattern = "^\\d{10}$"
        phone_title = "Enter a valid 10-digit phone number"
        for field_name in ['phone', 'father_mobile', 'mother_mobile', 'guardian_mobile']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'pattern': phone_pattern,
                    'title': phone_title,
                    'minlength': '10',
                    'maxlength': '10',
                    'type': 'tel'
                })

        if 'aadhar_number' in self.fields:
            self.fields['aadhar_number'].widget.attrs.update({
                'pattern': "^\\d{12}$",
                'title': "Enter a valid 12-digit Aadhar number",
                'minlength': '12',
                'maxlength': '12'
            })

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            today = datetime.date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 15:
                raise forms.ValidationError("You must be at least 15 years old to apply.")
        return dob

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            return email.lower()
        return email
