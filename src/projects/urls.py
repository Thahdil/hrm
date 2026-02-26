from django.urls import path
from . import views

urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('<int:pk>/', views.project_detail, name='project_detail'),
    path('add-hours/', views.add_project_hours, name='add_project_hours'),
    path('<int:pk>/toggle-status/', views.toggle_project_status, name='toggle_project_status'),
]

