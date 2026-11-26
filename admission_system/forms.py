from django import forms
import datetime
from django.contrib.auth.models import User
from .models import CREProfile, Application, Course
from .utils import is_username_taken, suggest_unique_username

class CRERegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    phone = forms.CharField(max_length=15, required=False)

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean_username(self):
        # Checked here (at submit time) as a server-side backstop for the
        # live AJAX check on the registration page - catches duplicates
        # even if JS is disabled or the username changed between the
        # live check and the final submit.
        username = (self.cleaned_data.get('username') or '').strip()
        if username and is_username_taken(username):
            suggestion = suggest_unique_username(username)
            if suggestion:
                raise forms.ValidationError(
                    f"The username '{username}' is already taken. "
                    f"Try '{suggestion}' instead."
                )
            raise forms.ValidationError(f"The username '{username}' is already taken.")
        return username

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
    doc_aadhar = forms.FileField(required=True, label="Aadhaar Card Copy")

    # Passport-size photo (stored on Student, not Application - it's a
    # student identity attribute, reused across colleges/applications).
    photo = forms.ImageField(
        required=True,
        label="Passport Size Photo",
        help_text="JPEG/PNG only, max 2MB, passport-style portrait photo."
    )

    class Meta:
        model = Student
        fields = [
            'name', 'dob', 'gender', 'aadhar_number', 'phone', 'email',
            'blood_group', 'category', 'permanent_address', 'correspondence_address',
            'state', 'city', 'father_name', 'father_mobile', 'father_occupation',
            'mother_name', 'mother_mobile', 'mother_occupation',
            'guardian_name', 'guardian_mobile', 'preferred_contact', 'photo'
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
        # Maps doc field name -> storage path already saved in the session
        # from an earlier step/attempt (apply_admission's pending_files).
        # P0 fix: this used to be a single has_files_in_session boolean that
        # made ALL FIVE document fields optional as soon as ANY one of them
        # had a pending file - so if, say, only the 10th marksheet had been
        # uploaded in an earlier attempt, the form would also silently let
        # the student submit with no Aadhaar document and no passport photo.
        # Tracking pending files per-field closes that gap, and also lets us
        # tell the template which specific fields already have a file
        # attached (see the 'data-pending-file' widget attr below), so the
        # file input doesn't appear to have "lost" an upload the user made
        # on a previous step/attempt.
        pending_files = kwargs.pop('pending_files', None) or {}
        super().__init__(*args, **kwargs)
        for doc_field in ('doc_10th', 'doc_11th', 'doc_12th', 'doc_aadhar', 'photo'):
            if doc_field in self.fields and doc_field in pending_files:
                self.fields[doc_field].required = False
                existing_name = str(pending_files[doc_field]).rsplit('/', 1)[-1]
                self.fields[doc_field].widget.attrs['data-pending-file'] = existing_name

        if college:
            self.fields['course'].queryset = college.courses.all()
            self.fields['course'].label_from_instance = lambda obj: f"{obj.name}"
        
        # Enforce mandatory selection for Gender and Aadhar
        self.fields['gender'].required = True
        self.fields['aadhar_number'].required = True

        # P1 fix: Student.dob/permanent_address/state/city/father_name/
        # father_mobile/mother_name/mother_mobile all have blank=True at the
        # model level (so other code, e.g. admin-created records, isn't
        # forced to fill them in) - which meant Django's ModelForm defaults
        # made every one of them optional here too, letting applicants skip
        # straight through the Location and Family steps with those fields
        # empty (bug reports: "No mandatory field validation for Location
        # Details and Family Details"). DOB specifically also silently
        # defeated clean_dob()'s minimum-age check below, since an empty
        # value never reaches it. Made required here, at the form level only
        # - the model stays permissive for other callers.
        self.fields['dob'].required = True
        self.fields['permanent_address'].required = True
        self.fields['state'].required = True
        self.fields['city'].required = True
        self.fields['father_name'].required = True
        self.fields['father_mobile'].required = True
        self.fields['mother_name'].required = True
        self.fields['mother_mobile'].required = True

        # Left optional deliberately (per an earlier, explicit product
        # decision recorded here - not changed, since bug-list Test 5/
        # Test 12/Test 15 asking to make some of these mandatory directly
        # conflicts with that decision and needs a product call, not a
        # unilateral code change):
        #   - blood_group, category: Neeraj Test 5 / Akhil Test 15 ask for
        #     these to be mandatory.
        #   - addon_course: Akhil Test 12 asks for this to be mandatory, but
        #     several courses have no add-ons configured at all, so a blanket
        #     requirement would block applicants to those courses entirely.
        self.fields['blood_group'].required = False
        self.fields['father_occupation'].required = False
        self.fields['mother_occupation'].required = False
        self.fields['correspondence_address'].required = False
        self.fields['category'].required = False
        
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
                'title': "Enter a valid 12-digit Aadhaar number",
                'minlength': '12',
                'maxlength': '12'
            })

        # P1 fix: State/City accepted numbers and special characters with no
        # validation. clean_state()/clean_city() above are the real
        # (server-side) enforcement; this just gives the same early,
        # in-browser feedback the name/phone/Aadhaar fields already get.
        place_pattern = "^[A-Za-z\\s.'-]+$"
        place_title = "Only letters, spaces, and hyphens are allowed"
        for field_name in ['state', 'city']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'pattern': place_pattern,
                    'title': place_title,
                })

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            today = datetime.date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 15:
                raise forms.ValidationError("You must be at least 15 years old to apply.")
            # P1 fix: the minimum-age check above had no corresponding upper
            # bound, so an obviously wrong date like 08-02-1842 (bug report)
            # passed straight through - it's "more than 15 years old" too.
            # 100 years is a generous ceiling for an applicant's age.
            if age > 100:
                raise forms.ValidationError("Enter a valid date of birth.")
        return dob

    def clean_state(self):
        state = (self.cleaned_data.get('state') or '').strip()
        if state and not re.fullmatch(r"[A-Za-z\s.'-]+", state):
            raise forms.ValidationError("State should only contain letters, spaces, and hyphens.")
        return state

    def clean_city(self):
        city = (self.cleaned_data.get('city') or '').strip()
        if city and not re.fullmatch(r"[A-Za-z\s.'-]+", city):
            raise forms.ValidationError("City should only contain letters, spaces, and hyphens.")
        return city

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            return email.lower()
        return email

    def clean_aadhar_number(self):
        """
        P0 fix: previously nothing stopped the same Aadhaar number being
        submitted for multiple different students - a serious identity/
        duplicate-admission integrity gap (bug report: "Duplicate Aadhaar
        Number Accepted Across Multiple Student Entries"). This enforces
        the 12-digit numeric format server-side (the client-side pattern=
        attr set in __init__ is cosmetic only and can't be trusted on its
        own) and rejects the number if it already belongs to a *different*
        student (matched by email, since Student has no other natural key
        here) - the same student re-applying for another course/college
        with their own Aadhaar number again is fine and expected.
        """
        aadhar_number = (self.cleaned_data.get('aadhar_number') or '').strip()
        if not aadhar_number:
            return aadhar_number

        if not re.fullmatch(r'\d{12}', aadhar_number):
            raise forms.ValidationError("Enter a valid 12-digit Aadhaar number.")

        existing = Student.objects.filter(aadhar_number=aadhar_number)
        this_email = (self.data.get('email') or self.initial.get('email') or '').strip().lower()
        if this_email:
            existing = existing.exclude(email__iexact=this_email)
        if existing.exists():
            raise forms.ValidationError(
                "This Aadhaar number is already registered with another student. "
                "If this is a mistake, please contact the administrator."
            )
        return aadhar_number

    def _clean_10_digit_mobile(self, field_name, required):
        """
        P2 fix: phone/father_mobile/mother_mobile/guardian_mobile only had a
        client-side `pattern` attribute (set in __init__) enforcing 10
        digits - cosmetic only, since it's trivially bypassed (disabled JS,
        browser devtools, or a direct POST) and nothing stopped letters or
        symbols from reaching the database (bug report: "Aadhaar Number and
        Phone Number fields accept alphabetic characters" - Aadhaar itself
        was already covered by clean_aadhar_number above; this closes the
        same gap for every mobile-number field).
        """
        value = (self.cleaned_data.get(field_name) or '').strip()
        if not value:
            if required:
                raise forms.ValidationError("This field is required.")
            return value
        if not re.fullmatch(r'\d{10}', value):
            raise forms.ValidationError("Enter a valid 10-digit phone number.")
        return value

    def clean_phone(self):
        return self._clean_10_digit_mobile('phone', required=True)

    def clean_father_mobile(self):
        return self._clean_10_digit_mobile('father_mobile', required=False)

    def clean_mother_mobile(self):
        return self._clean_10_digit_mobile('mother_mobile', required=False)

    def clean_guardian_mobile(self):
        return self._clean_10_digit_mobile('guardian_mobile', required=False)
