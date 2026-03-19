import csv
from django.http import HttpResponse
from django.contrib import admin
from .models import College, Course, CREProfile, Student, Application

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
    list_display = ('name', 'college')
    list_filter = ('college',)

@admin.register(CREProfile)
class CREProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'cre_id', 'phone')
    search_fields = ('user__username', 'cre_id')
    filter_horizontal = ('allocated_colleges',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
    search_fields = ('name', 'email')
    actions = [export_as_csv]

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('student', 'college', 'course', 'referred_by', 'applied_at')
    list_filter = ('college', 'referred_by', 'applied_at')
    search_fields = ('student__name', 'referred_by__user__username')
    actions = [export_as_csv]
