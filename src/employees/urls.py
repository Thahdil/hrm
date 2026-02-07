from django.urls import path
from . import views

urlpatterns = [
    path('', views.employee_list, name='employee_list'),
    path('add/', views.employee_create, name='employee_add'),
    path('edit/<int:pk>/', views.employee_edit, name='employee_edit'),
    path('delete/<int:pk>/', views.employee_delete, name='employee_delete'),
    path('restore/<int:pk>/', views.employee_restore, name='employee_restore'),
    path('restore/bulk/', views.employee_bulk_restore, name='employee_bulk_restore'),
    path('delete/permanent/<int:pk>/', views.employee_permanent_delete, name='employee_permanent_delete'),
    path('documents/', views.document_list, name='document_list'),
    path('documents/upload/', views.document_upload, name='document_upload'),
    path('my-profile/', views.my_profile, name='my_profile'),
]
