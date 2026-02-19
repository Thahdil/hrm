from django.urls import path
from . import views

urlpatterns = [
    path('', views.meeting_list, name='meeting_list'),
    path('schedule/', views.schedule_meeting, name='meeting_schedule'),
    path('<int:pk>/', views.meeting_detail, name='meeting_detail'),
    path('<int:pk>/cancel/', views.meeting_delete, name='meeting_delete'),
    path('<int:pk>/add-participants/', views.add_participants, name='meeting_add_participants'),
]
