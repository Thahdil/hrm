from django.urls import path
from . import views, views_document

urlpatterns = [
    path('leave-requests/', views.leave_list, name='leave_list'),
    path('leave-requests/add/', views.leave_create, name='leave_add'),
    path('leave-requests/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leave-requests/<int:pk>/delete/', views.leave_delete, name='leave_delete'),
    path('leave-requests/<int:pk>/action/', views.leave_approve, name='leave_approve'),
    path('leave-requests/<int:pk>/upload/', views_document.leave_upload_document, name='leave_upload_document'),
    path('leave-requests/<int:pk>/verify/', views_document.leave_verify_document, name='leave_verify_document'),
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/add/', views.ticket_create, name='ticket_add'),
    # Configuration
    path('settings/', views.leave_settings, name='leave_settings'),
    path('settings/add/', views.leave_type_add, name='leave_type_add'),
    path('settings/<int:pk>/edit/', views.leave_type_edit, name='leave_type_edit'),
    path('settings/<int:pk>/delete/', views.leave_type_delete, name='leave_type_delete'),
    path('settings/<int:pk>/restore/', views.leave_type_restore, name='leave_type_restore'),
    
    # API for live updates
    path('api/check-updates/', views.check_updates, name='api_check_updates'),
    
    # LOP Adjustments
    path('lop-adjustments/', views.lop_adjustment_list, name='lop_adjustment_list'),
    path('lop-adjustments/request/', views.lop_adjustment_request, name='lop_adjustment_request'),
    path('lop-adjustments/request/<int:payroll_id>/', views.lop_adjustment_request, name='lop_adjustment_request_payroll'),
    path('lop-adjustments/<int:pk>/', views.lop_adjustment_detail, name='lop_adjustment_detail'),
    path('lop-adjustments/<int:pk>/approve/', views.lop_adjustment_approve, name='lop_adjustment_approve'),
    path('lop-adjustments/<int:pk>/delete/', views.lop_adjustment_delete, name='lop_adjustment_delete'),
    path('lop-adjustments/log/', views.lop_adjustment_report, name='lop_adjustment_log'),
    path('lop-adjustments/bulk/', views.lop_adjustment_bulk, name='lop_adjustment_bulk'),
]
