from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import DocumentVault
from .forms import EmployeeForm, DocumentForm
from .forms import EmployeeForm, DocumentForm
from django.contrib.auth import get_user_model
from core.models import AuditLog

@login_required
def employee_list(request):
    if not (request.user.is_superuser or request.user.is_admin() or request.user.is_hr() or request.user.is_ceo()):
         return redirect('dashboard')
         
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Q
    User = get_user_model()
    
    # Query parameters
    status_filter = request.GET.get('status', 'active')
    dept_filter = request.GET.get('department', '')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    if status_filter == 'archived':
        queryset = User.objects.filter(role='EMPLOYEE', status='ARCHIVED')
    else:
        queryset = User.objects.filter(role='EMPLOYEE', is_active=True).exclude(status='ARCHIVED')
    
    # Apply Department Filter
    if dept_filter:
        queryset = queryset.filter(department=dept_filter)
        
    # Apply Search Query
    if search_query:
        search_id = search_query.replace('EMP-', '').replace('emp-', '')
        search_filter = Q(full_name__icontains=search_query) | \
                       Q(username__icontains=search_query) | \
                       Q(employee_id__icontains=search_query) | \
                       Q(designation__icontains=search_query)
        
        if search_id.isdigit():
            search_filter |= Q(id=search_id)
            
        queryset = queryset.filter(search_filter)
        
    employees = queryset.order_by('-date_joined').prefetch_related('documents', 'leave_requests')
    
    today = timezone.localdate()
    
    # Enhance employee objects with computed status for the dashboard
    for emp in employees:
        # 1. On Leave Status
        # Check if leave_requests relation exists (it should via FK related_name)
        if hasattr(emp, 'leave_requests'):
            emp.is_on_leave = emp.leave_requests.filter(
                status='APPROVED', 
                start_date__lte=today, 
                end_date__gte=today
            ).exists()
        else:
            emp.is_on_leave = False
        
        # 2. Expiry Warnings
        emp.has_expiry_warning = False
        if hasattr(emp, 'documents'):
            docs = emp.documents.all()
            for doc in docs:
                if doc.expiry_date and doc.expiry_date <= today + timedelta(days=30):
                    emp.has_expiry_warning = True
                    break
                
        # 3. Gratuity Accrued (Indian Estimate: 15/26 * Basic * Years)
        if emp.date_of_joining:
            years = (today - emp.date_of_joining).days / 365.25
            if years >= 4.8:
                daily = (float(emp.salary_basic) / 26) if emp.salary_basic else 0
                emp.gratuity_estimate = round(years * 15 * daily, 2)
            else:
                emp.gratuity_estimate = 0
        else:
            emp.gratuity_estimate = 0
            
    return render(request, 'employees/employee_list.html', {
        'employees': employees, 
        'current_status': status_filter,
        'search_query': search_query,
        'dept_filter': dept_filter,
        'departments': User.Department.choices,
        'total_count': employees.count(),
        'all_employee_names': User.objects.filter(role='EMPLOYEE', is_active=True).values_list('full_name', flat=True)
    })

@login_required
def employee_create(request):
    if not (request.user.is_superuser or request.user.is_admin() or request.user.is_hr() or request.user.is_ceo()):
         messages.error(request, "Permission denied.")
         return redirect('dashboard')
         
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            emp = form.save()
            messages.success(request, "Employee created successfully!")
            return redirect('employee_list')
    else:
        form = EmployeeForm()
    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Add New Employee'})

@login_required
def employee_edit(request, pk):
    if not (request.user.is_superuser or request.user.is_admin() or request.user.is_hr() or request.user.is_ceo()):
         messages.error(request, "Permission denied.")
         return redirect('dashboard')
         
    User = get_user_model()
    # pk is now user_id
    employee = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, "Employee updated successfully!")
            return redirect('employee_list')
    else:
        form = EmployeeForm(instance=employee)
    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Edit Employee'})

@login_required
def document_list(request):
    user = request.user
    if user.is_staff or (hasattr(user, 'role') and user.role in ['ADMIN', 'HR_MANAGER', 'CEO']):
        documents = DocumentVault.objects.select_related('employee').all().order_by('expiry_date')
    else:
        # ESS: Only own documents
        documents = DocumentVault.objects.select_related('employee').filter(employee=user).order_by('expiry_date')
            
    return render(request, 'employees/document_list.html', {'documents': documents})

@login_required
def document_upload(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            doc = form.save(commit=False)
            # If standard user, force own ID
            if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'CEO'])):
                doc.employee = request.user
            doc.save()
            messages.success(request, "Document uploaded successfully!")
            return redirect('document_list')
    else:
        form = DocumentForm(user=request.user)
    return render(request, 'employees/document_form.html', {'form': form, 'title': 'Upload Document'})

@login_required
def my_profile(request):
    employee = request.user
        
    if request.method == 'POST':
        # Limit what employees can edit safely
        username = request.POST.get('username')
        email = request.POST.get('email')
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone_number')
        iban = request.POST.get('iban')
        ifsc = request.POST.get('ifsc_code')
        pan = request.POST.get('pan_number')
        address = request.POST.get('address')
        dob = request.POST.get('date_of_birth')
        gender = request.POST.get('gender')
        designation = request.POST.get('designation')
        
        # Update fields
        if username: employee.username = username
        if email: employee.email = email
        if full_name: employee.full_name = full_name
        if phone: employee.phone_number = phone
        if iban: employee.iban = iban
        if ifsc: employee.ifsc_code = ifsc
        if pan: employee.pan_number = pan
        if address: employee.address = address
        if dob: employee.date_of_birth = dob
        if gender: employee.gender = gender
        if designation: employee.designation = designation

        # Handle file uploads if any (e.g. avatar later)
        if request.FILES.get('profile_picture'):
             # Future: Handle avatar upload
             pass

        try:
            employee.save()
            messages.success(request, "Profile updated successfully.")
        except Exception as e:
            messages.error(request, f"Error updating profile: {e}")
            
        return redirect('my_profile')

    return render(request, 'employees/my_profile.html', {
        'employee': employee,
        'designation_choices': employee.Designation.choices
    })

@login_required
def employee_delete(request, pk):
    User = get_user_model()
    employee = get_object_or_404(User, pk=pk)
    
    # Permission Check: specific to project roles
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
         messages.error(request, "You do not have permission to delete employees.")
         return redirect('employee_list')

    if request.method == 'POST':
        username = employee.username
        # Safety: Prevent deleting self
        if employee.id == request.user.id:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({'status': 'error', 'message': "You cannot delete your own account."}, status=403)
            messages.error(request, "You cannot delete your own account.")
            return redirect('employee_list')
            
        # SOFT DELETE LOGIC
        employee.is_active = False
        employee.status = User.Status.ARCHIVED
        employee.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'status': 'success', 'message': f"Employee {username} has been archived successfully."})
        
        messages.success(request, f"Employee {username} has been archived successfully.")
    
    return redirect('employee_list')

@login_required
def employee_restore(request, pk):
    User = get_user_model()
    employee = get_object_or_404(User, pk=pk)
    
    # Permission Check
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
         messages.error(request, "Permission denied.")
         return redirect('employee_list')
         
    if request.method == 'POST':
        employee.is_active = True
        employee.status = User.Status.ACTIVE
        employee.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'status': 'success', 'message': f"Employee {employee.username} restored successfully."})
            
        messages.success(request, f"Employee {employee.username} restored successfully.")
        
    return redirect('employee_list')

@login_required
def employee_permanent_delete(request, pk):
    User = get_user_model()
    employee = get_object_or_404(User, pk=pk)

    # Strict Permission Check (Admin/CEO Only)
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'CEO'])):
         messages.error(request, "Permission denied. Only Admins can permanently delete users.")
         return redirect('employee_list')

    if request.method == 'POST':
        username = employee.username
        if employee.id == request.user.id:
             messages.error(request, "You cannot delete your own account.")
             return redirect('employee_list')
             
        try:
            # MANUAL CASCADE DELETE
            # 1. Delete Payroll Entries (Protected Relation - Default related_name is payrollentry_set)
            if hasattr(employee, 'payrollentry_set'):
                employee.payrollentry_set.all().delete()
            
            # 2. Delete Attendance Logs (Usually Cascade)
            if hasattr(employee, 'attendance_logs'):
                employee.attendance_logs.all().delete()
            
            # 3. Delete Leave Requests & Balances
            if hasattr(employee, 'leave_requests'):
                employee.leave_requests.all().delete()
            if hasattr(employee, 'leave_balances'):
                employee.leave_balances.all().delete()
            if hasattr(employee, 'ticket_requests'):
                employee.ticket_requests.all().delete()

            # 4. Delete Documents
            if hasattr(employee, 'documents'):
                employee.documents.all().delete()
            
            # Finally, delete the User
            employee.delete()
            messages.success(request, f"Employee {username} and all related data permanently deleted.")
            
        except Exception as e:
            messages.error(request, f"Error deleting employee: {str(e)}")

    return redirect('employee_list')

@login_required
def employee_bulk_restore(request):
    User = get_user_model()
    
    # Permission Check
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
         messages.error(request, "Permission denied.")
         return redirect('employee_list')

    if request.method == 'POST':
        user_ids = request.POST.getlist('user_ids')
        if user_ids:
            # Filter users who are archived based on IDs
            restored_count = User.objects.filter(id__in=user_ids, status=User.Status.ARCHIVED).update(is_active=True, status=User.Status.ACTIVE)
            if restored_count > 0:
                messages.success(request, f"{restored_count} employees restored successfully.")
            else:
                messages.info(request, "No eligible archived employees found in selection.")
        else:
            messages.warning(request, "No employees selected.")
            
    return redirect('employee_list')
