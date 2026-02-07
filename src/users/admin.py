from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Role & Status', {'fields': ('role', 'status')}),
        ('Employment Details', {'fields': ('department', 'designation', 'salary_basic', 'salary_allowance', 'contract_type', 'date_of_joining', 'aadhaar_number', 'ifsc_code')}),
        ('Personal Info', {'fields': ('phone_number', 'address', 'date_of_birth', 'gender')}),
    )
    list_display = ('id', 'username', 'email', 'role', 'status', 'department', 'designation')
    list_filter = ('role', 'status', 'department', 'is_staff')
    search_fields = ('id', 'username', 'email', 'first_name', 'last_name', 'aadhaar_number')
