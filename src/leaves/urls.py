from django.urls import path
from . import views

urlpatterns = [
    path('leave-requests/', views.leave_list, name='leave_list'),
    path('leave-requests/add/', views.leave_create, name='leave_add'),
    path('leave-requests/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leave-requests/<int:pk>/delete/', views.leave_delete, name='leave_delete'),
    path('leave-requests/<int:pk>/action/', views.leave_approve, name='leave_approve'),
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/add/', views.ticket_create, name='ticket_add'),
    # Configuration
    path('settings/', views.leave_settings, name='leave_settings'),
    path('settings/add/', views.leave_type_add, name='leave_type_add'),
    path('settings/<int:pk>/edit/', views.leave_type_edit, name='leave_type_edit'),
    path('settings/<int:pk>/delete/', views.leave_type_delete, name='leave_type_delete'),
    path('settings/<int:pk>/restore/', views.leave_type_restore, name='leave_type_restore'),
]
