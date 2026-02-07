from django.urls import path
from . import views

urlpatterns = [
    path('batches/', views.payroll_list, name='payroll_list'),
    path('batches/<int:pk>/', views.payroll_detail, name='payroll_detail'),
    path('my-payslips/', views.my_payslips, name='my_payslips'),
    path('my-attendance/', views.my_attendance, name='my_attendance'),
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/import/', views.attendance_import, name='attendance_import'),
    path('attendance/clear/', views.clear_attendance_logs, name='clear_attendance_logs'),
    path('attendance/manual-entry/', views.attendance_manual_entry, name='attendance_manual_entry'),
    path('run-payroll/', views.run_payroll_action, name='run_payroll'),
    path('gratuity-report/', views.gratuity_report, name='gratuity_report'),
    path('api/employee-autocomplete/', views.employee_autocomplete, name='employee_autocomplete'),
    path('batches/delete/<int:pk>/', views.payroll_batch_delete, name='payroll_batch_delete'),
    path('batches/void/<int:pk>/', views.payroll_batch_void, name='payroll_batch_void'),
]
