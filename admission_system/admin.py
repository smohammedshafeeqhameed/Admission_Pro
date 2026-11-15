import csv
from django.http import HttpResponse
from django.contrib import admin
from .models import College, Course, CREProfile, FinanceProfile, Student, Application, ApplicationSource, AddonCourse, CampusManagerProfile, AcademicYear

# ... (rest of the code)

@admin.register(CampusManagerProfile)
class CampusManagerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'college', 'phone')
    list_filter = ('college',)
    search_fields = ('user__username', 'phone')

@admin.action(description="Export Selected as CSV")
def export_as_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    field_names = [field.name for field in meta.fields]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={meta}.csv'
    writer = csv.writer(response)

    writer.writerow(field_names)
    for obj in queryset:
        row = writer.writerow([getattr(obj, field) for field in field_names])

    return response

@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ('name', 'theme_color', 'slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'college', 'total_seats', 'occupied_seats', 'available_seats_display')
    list_filter = ('college',)
    list_editable = ('total_seats',)
    readonly_fields = ('occupied_seats',)

    @admin.display(description='Available Seats')
    def available_seats_display(self, obj):
        return obj.available_seats

@admin.register(CREProfile)
class CREProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'cre_id', 'phone')
    search_fields = ('user__username', 'cre_id')
    filter_horizontal = ('allocated_colleges',)

    def save_model(self, request, obj, form, change):
        # Stashed so the m2m_changed signal (models.py) can build an
        # absolute referral-link URL when allocated_colleges is saved
        # just after this, via form.save_m2m() in save_related().
        obj._notification_request = request
        super().save_model(request, obj, form, change)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('photo_thumbnail', 'name', 'email', 'phone')
    search_fields = ('name', 'email')
    actions = [export_as_csv]
    readonly_fields = ('photo_preview',)
    fields = ('photo', 'photo_preview', 'name', 'email', 'phone', 'dob', 'gender', 'aadhar_number',
              'blood_group', 'category', 'permanent_address', 'correspondence_address', 'state', 'city',
              'father_name', 'father_mobile', 'father_occupation',
              'mother_name', 'mother_mobile', 'mother_occupation',
              'guardian_name', 'guardian_mobile', 'preferred_contact')

    @admin.display(description='Photo')
    def photo_thumbnail(self, obj):
        from django.utils.html import format_html
        if obj.photo:
            return format_html('<img src="{}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;" />', obj.photo.url)
        return "—"

    @admin.display(description='Photo Preview')
    def photo_preview(self, obj):
        from django.utils.html import format_html
        if obj.photo:
            return format_html('<img src="{}" style="width:160px;height:160px;border-radius:12px;object-fit:cover;" />', obj.photo.url)
        return "No photo uploaded"

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('student', 'college', 'course', 'referred_by', 'closed_by', 'status', 'payment_status', 'eligible_for_commission', 'commission_status', 'commission_amount', 'applied_at')
    list_filter = ('college', 'status', 'payment_status', 'eligible_for_commission', 'commission_status', 'referred_by', 'applied_at')
    search_fields = ('student__name', 'referred_by__user__username')
    actions = [export_as_csv]

@admin.register(FinanceProfile)
class FinanceProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone')
    search_fields = ('user__username',)

@admin.register(ApplicationSource)
class ApplicationSourceAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(AddonCourse)
class AddonCourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'course')

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_currently_active', 'is_current')
    ordering = ('-start_date',)
    list_editable = ('is_current',)

    @admin.display(description='Active Now?', boolean=True)
    def is_currently_active(self, obj):
        # The year actually picked by AcademicYear.get_current() right now -
        # i.e. what the portal's "Current Academic Year" default resolves
        # to - as distinct from the manually-set `is_current` fallback flag.
        return obj == AcademicYear.get_current()