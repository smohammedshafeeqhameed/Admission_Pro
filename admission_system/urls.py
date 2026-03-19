from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.CRERegistrationView.as_view(), name='register_cre'),
    path('login/', views.CRELoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.DashboardView.as_view(), name='cre_dashboard'),
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin-dashboard/allocate/', views.AdminAllocateCollegeView.as_view(), name='admin_allocate_college'),
    path('admin-dashboard/export/', views.AdminExportCSVView.as_view(), name='admin_export_csv'),
    path('apply/<slug:college_slug>/<uuid:cre_id>/', views.apply_admission, name='apply_admission'),
]
