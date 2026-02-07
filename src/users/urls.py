from django.urls import path
from . import views
from . import views_otp

urlpatterns = [
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_create, name='user_create'),
    path('users/edit/<int:pk>/', views.user_edit, name='user_edit'),
    path('my-team/', views.manage_team_assignments, name='manage_team_assignments'),
    
    # Password Management
    path('change-password/', views.change_password, name='change_password'),
    path('reset-password/', views_otp.password_reset_request, name='password_reset_request'),
    path('reset-password/verify/', views_otp.password_reset_verify, name='password_reset_verify'),
]
