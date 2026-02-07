from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.static import static
from core.views import dashboard, serve_secure_document, system_admin, system_logs, company_profile, public_holiday_add, public_holiday_delete, holiday_settings
from core.auth_views import CustomLoginView, CustomLogoutView

from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    # Secure Media Serving
    path('media/secure_docs/<path:path>', serve_secure_document, name='serve_secure_document'),
    
    path('', dashboard, name='dashboard'),
    path('employees/', include('employees.urls')),
    path('payroll/', include('payroll.urls')),
    path('leaves/', include('leaves.urls')),
    path('system-admin/', system_admin, name='system_admin'),
    path('system-admin/logs/', system_logs, name='system_logs'),
    path('system-admin/company-profile/', company_profile, name='company_profile'),
    path('system-admin/holidays/', holiday_settings, name='holiday_settings'),
    path('system-admin/company-profile/holiday/add/', public_holiday_add, name='public_holiday_add'),
    path('system-admin/company-profile/holiday/delete/<int:pk>/', public_holiday_delete, name='public_holiday_delete'),
    path('administration/', include('users.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
