from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from employees.models import DocumentVault
from leaves.models import LeaveRequest
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
import os
from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseForbidden
import mimetypes

@login_required
def serve_secure_document(request, path):
    file_path = os.path.join(settings.MEDIA_ROOT, 'secure_docs', path)
    
    if not os.path.exists(file_path):
        raise Http404("Document not found")

    # Granular Permission Check
    # 1. Identify which document this file belongs to
    # We try to reverse-lookup the document via the relative path
    # 'secure_docs/2024/01/filename.pdf' -> field 'file' contains 'secure_docs/2024/01/filename.pdf'
    relative_path = os.path.join('secure_docs', path)
    
    # Attempt to find the vault entry
    try:
        from employees.models import DocumentVault
        doc = DocumentVault.objects.get(file=relative_path)
        
        # 2. Check Ownership or Role
        is_owner = (doc.employee == request.user)
        is_admin_hr = (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO']))
        
        if not (is_owner or is_admin_hr):
             return HttpResponseForbidden("You are not authorized to view this confidential document.")
             
    except DocumentVault.DoesNotExist:
        # If no DB record found (orphaned file?), default to Admin only
        if not request.user.is_staff and request.user.role != 'ADMIN':
             return HttpResponseForbidden("Unauthorized access to unlinked document.")

    content_type, encoding = mimetypes.guess_type(file_path)
    content_type = content_type or 'application/octet-stream'

    # Determine if we should view (inline) or download (attachment)
    action = request.GET.get('action', 'view')
    disposition = 'inline' if action == 'view' else 'attachment'

    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type=content_type)
        response['Content-Disposition'] = f'{disposition}; filename="{os.path.basename(file_path)}"'
        return response

@login_required
def system_admin(request):
    user = request.user
    if not user.is_staff and not (user.is_admin() or user.is_ceo()):
        return redirect('dashboard')
        
    # Stats for the admin panel
    User = get_user_model()
    total_users = User.objects.count()
    admin_users = User.objects.filter(role='ADMIN').count()
    
    context = {
        'total_users': total_users,
        'admin_users': admin_users
    }
    return render(request, 'system_admin.html', context)

@login_required
def system_logs(request):
    user = request.user
    if not user.is_staff and not (user.is_admin() or user.is_ceo()):
        return redirect('dashboard')
        
    from .models import AuditLog
    
    # Get filter parameters
    module_filter = request.GET.get('module', '')
    action_filter = request.GET.get('action', '')
    
    logs = AuditLog.objects.select_related('user', 'content_type').order_by('-timestamp')
    
    if module_filter:
        logs = logs.filter(module=module_filter)
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    logs = logs[:200]  # Limit to 200 most recent
    
    context = {
        'logs': logs,
        'modules': AuditLog.Module.choices,
        'actions': AuditLog.Action.choices,
        'selected_module': module_filter,
        'selected_action': action_filter,
    }
    
    return render(request, 'system_logs.html', context)

@login_required
def company_profile(request):
    user = request.user
    if not user.is_staff and not (user.is_admin() or user.is_ceo()):
        return redirect('dashboard')
        
    from .models import CompanySettings
    from .forms import CompanySettingsForm
    from django.contrib import messages
    
    settings_obj = CompanySettings.load()
    
    if request.method == 'POST':
        form = CompanySettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Company Profile updated successfully.")
            return redirect('system_admin')
    else:
        form = CompanySettingsForm(instance=settings_obj)
        
    return render(request, 'company_profile.html', {
        'form': form,
    })

@login_required
def holiday_settings(request):
    user = request.user
    if not user.is_staff and not (user.is_admin() or user.is_ceo()):
        return redirect('dashboard')
        
    from .models import PublicHoliday
    from .forms import PublicHolidayForm
    
    holidays = PublicHoliday.objects.all().order_by('date')
    holiday_form = PublicHolidayForm()
        
    return render(request, 'holiday_settings.html', {
        'holidays': holidays,
        'holiday_form': holiday_form
    })

@login_required
def public_holiday_add(request):
    if not request.user.is_staff and not (request.user.is_admin() or request.user.is_ceo()):
         return redirect('dashboard')
         
    from .forms import PublicHolidayForm
    from django.contrib import messages
    
    if request.method == 'POST':
        form = PublicHolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save()
            
            from .models import AuditLog
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                obj=holiday,
                request=request,
                module=AuditLog.Module.SYSTEM,
                object_repr=holiday.name
            )
            
            messages.success(request, "Holiday added.")
        else:
            messages.error(request, "Error adding holiday.")
            
    return redirect('holiday_settings')

@login_required
def public_holiday_delete(request, pk):
    if not request.user.is_staff and not (request.user.is_admin() or request.user.is_ceo()):
         return redirect('dashboard')
         
    from .models import PublicHoliday
    from django.contrib import messages
    
    try:
        holiday = PublicHoliday.objects.get(pk=pk)
        holiday_name = holiday.name
        holiday.delete()
        
        from .models import AuditLog
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.DELETE,
            obj=None, # Object deleted
            request=request,
            module=AuditLog.Module.SYSTEM,
            object_repr=holiday_name
        )
        
        messages.success(request, "Holiday removed.")
    except PublicHoliday.DoesNotExist:
        pass
        
    return redirect('holiday_settings')

@login_required
def dashboard(request):
    user = request.user
    
    # --- ADMIN / HR DASHBOARD ---
    if user.is_staff or user.is_admin() or user.is_hr() or user.is_ceo():
        from django.contrib.auth import get_user_model
        from .models import PublicHoliday
        User = get_user_model()
        
        # Statistics for the Admin Dashboard
        today = timezone.now().date()
        current_month = today.month
        current_year = today.year
        
        # 1. Total Employees & New Joiners
        total_employees = User.objects.filter(role='EMPLOYEE').count()
        new_employees_count = User.objects.filter(role='EMPLOYEE', date_joined__month=current_month, date_joined__year=current_year).count()
        if total_employees > 0 and new_employees_count > 0:
            new_emp_percentage = round((new_employees_count / total_employees) * 100, 1)
        else:
            new_emp_percentage = 0
            
        # 2. Active Today (Attendance)
        from payroll.models import AttendanceLog
        active_today_count = AttendanceLog.objects.filter(date=today, is_absent=False).count()
        
        # Calculate Attendance Rate
        active_employees_count = User.objects.filter(role='EMPLOYEE', status='ACTIVE').count()
        if active_employees_count > 0:
            attendance_rate = round((active_today_count / active_employees_count) * 100, 1)
        else:
            attendance_rate = 0
            
        # 3. On Leave & Pending Approvals
        on_leave_count = LeaveRequest.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            status=LeaveRequest.Status.APPROVED
        ).count()
        
        pending_approvals_count = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count()
        
        # 4. Expiring Documents (Next 30 days)
        expiry_threshold = today + timedelta(days=30)
        expiring_docs_count = DocumentVault.objects.filter(expiry_date__range=[today, expiry_threshold]).count()
        
        # Pending Leave Requests List
        pending_leave_requests = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).select_related('employee', 'leave_type').order_by('-created_at')[:10]
        pending_leaves = pending_leave_requests # Use the queryset for iteration in template
        
        # Upcoming Holidays
        upcoming_holidays = PublicHoliday.objects.filter(date__gte=today).order_by('date')[:5]
        
        # Calculate Total Gratuity Liability
        from payroll.services import GratuityService
        from decimal import Decimal
        
        total_liability = Decimal('0.00')
        active_emps = User.objects.filter(role='EMPLOYEE', status='ACTIVE')
        for emp in active_emps:
            service = GratuityService(emp)
            result = service.calculate()
            total_liability += result['amount']
        
        # Attendance rate (mock for now - you can calculate actual)
        attendance_rate = 95
        
        # Recent Activities from Audit Log
        from .models import AuditLog
        recent_activities = AuditLog.objects.select_related('user').exclude(
            action__in=[AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT]
        ).exclude(
            # Exclude Profile Updates (User/Employee Updates)
            module__in=[AuditLog.Module.EMPLOYEES, AuditLog.Module.USERS],
            action=AuditLog.Action.UPDATE
        ).exclude(
            action=AuditLog.Action.UPDATE,
            changes=None
        ).order_by('-timestamp')[:10]
        
        # Leave Balance for current user (if they're also an employee)
        leave_balances = []
        if user.role == 'EMPLOYEE' or hasattr(user, 'subordinates'):
            from leaves.models import LeaveBalance, LeaveType
            try:
                # Get only active leave types
                leave_types = LeaveType.objects.filter(is_active=True)
                current_year = today.year
                
                for leave_type in leave_types:
                    try:
                        balance = LeaveBalance.objects.get(
                            employee=user,
                            leave_type=leave_type,
                            year=current_year
                        )
                        leave_balances.append({
                            'name': leave_type.name,
                            'code': leave_type.code,
                            'used': balance.days_used,
                            'total': balance.total_entitlement,
                            'remaining': balance.remaining,
                            'percentage': int((balance.days_used / balance.total_entitlement * 100) if balance.total_entitlement > 0 else 0)
                        })
                    except LeaveBalance.DoesNotExist:
                        # Create balance if it doesn't exist
                        balance = LeaveBalance.objects.create(
                            employee=user,
                            leave_type=leave_type,
                            year=current_year,
                            total_entitlement=leave_type.days_entitlement,
                            days_used=0
                        )
                        leave_balances.append({
                            'name': leave_type.name,
                            'code': leave_type.code,
                            'used': 0,
                            'total': leave_type.days_entitlement,
                            'remaining': leave_type.days_entitlement,
                            'percentage': 0
                        })
            except Exception as e:
                # Fallback to default values
                leave_balances = [
                    {'name': 'Annual Leave', 'code': 'ANN', 'used': 12, 'total': 30, 'remaining': 18, 'percentage': 40},
                    {'name': 'Sick Leave', 'code': 'SICK', 'used': 3, 'total': 15, 'remaining': 12, 'percentage': 20},
                    {'name': 'Personal Leave', 'code': 'PERS', 'used': 1, 'total': 5, 'remaining': 4, 'percentage': 20}
                ]
        
        context = {
            'total_employees': total_employees,
            'new_employees_count': new_employees_count,
            'new_emp_percentage': new_emp_percentage,
            
            'active_today_count': active_today_count,
            'attendance_rate': attendance_rate,
            
            'on_leave_count': on_leave_count,
            'pending_approvals_count': pending_approvals_count,
            
            'active_employees': active_employees_count, # kept for backward compat if used elsewhere
            'expiring_docs_count': expiring_docs_count,
            'pending_leaves': pending_leaves,
            'pending_leave_requests': pending_leave_requests,
            'total_gratuity_liability': total_liability,
            'upcoming_holidays': upcoming_holidays,
            'recent_activities': recent_activities,
            'leave_balances': leave_balances,
        }
        return render(request, 'dashboard_modern.html', context)
    
    # --- EMPLOYEE SELF-SERVICE (ESS) DASHBOARD ---
    else:
        # User IS the employee
        employee = user

        # Context Data
        recent_leaves = LeaveRequest.objects.filter(employee=user).order_by('-created_at')[:5]
        
        # Attendance
        today = timezone.now()
        from payroll.models import AttendanceLog
        attendance_count = AttendanceLog.objects.filter(
            employee=user, 
            date__month=today.month,
            is_absent=False
        ).count()

        # Leave Balances for ESS
        from leaves.models import LeaveBalance, LeaveType
        leave_balances = []
        from django.db.models import Q
        try:
            # Filter Leave Types based on Gender Eligibility
            leave_types = LeaveType.objects.filter(is_active=True)
            if user.gender:
                leave_types = leave_types.filter(Q(eligibility_gender='ALL') | Q(eligibility_gender=user.gender))
            else:
                # If gender not specified, only show 'ALL' to be safe
                leave_types = leave_types.filter(eligibility_gender='ALL')

            for lt in leave_types:
                # Calculate proper entitlement
                is_fixed_monthly = (lt.accrual_frequency == 'MONTHLY' and (lt.duration_days == 1 or 'Sick' in lt.name or 'Normal' in lt.name))
                
                if is_fixed_monthly:
                    # Non-accumulative: 1 day per month
                    total_quota = 1.0
                    # Calculate used THIS MONTH specifically
                    days_used = LeaveRequest.objects.filter(
                        employee=user,
                        leave_type=lt,
                        status=LeaveRequest.Status.APPROVED,
                        start_date__month=today.month,
                        start_date__year=today.year
                    ).count()
                    used = float(days_used)
                else:
                    # Standard logic
                    total_quota = lt.days_entitlement
                    if lt.accrual_frequency == 'MONTHLY':
                        # Prorate based on current month (Month 1 = 1/12th, Month 12 = 12/12ths)
                        total_quota = (lt.days_entitlement / 12) * today.month

                    balance_obj, created = LeaveBalance.objects.get_or_create(
                        employee=user,
                        leave_type=lt,
                        year=today.year,
                        defaults={'total_entitlement': total_quota, 'days_used': 0}
                    )
                    
                    if not created and balance_obj.total_entitlement != total_quota:
                        balance_obj.total_entitlement = total_quota
                        balance_obj.save()
                    
                    used = float(balance_obj.days_used)
                    total_quota = float(balance_obj.total_entitlement)

                remaining = total_quota - used
                percentage = int((used / total_quota * 100) if total_quota > 0 else 0)

                leave_balances.append({
                    'name': lt.name,
                    'code': lt.code,
                    'used': used,
                    'total': total_quota,
                    'remaining': max(0, remaining),
                    'percentage': percentage,
                    'remaining_percentage': 100 - percentage
                })
        except:
            pass

        # Additional ESS Stats
        pending_leaves_count = LeaveRequest.objects.filter(employee=user, status=LeaveRequest.Status.PENDING).count()
        total_leave_used = sum(b['used'] for b in leave_balances)
        
        # Simple attendance rate for current month
        days_in_month = today.day
        # Average Attendance for ALL Employees (Requested Feature)
        total_present_logs = AttendanceLog.objects.filter(
            date__month=today.month,
            date__year=today.year,
            status__in=['Present', 'HalfDay']
        ).count()
        avg_daily_attendance = int(total_present_logs / days_in_month) if days_in_month > 0 else 0

        # Upcoming Holidays
        from .models import PublicHoliday
        upcoming_holidays = PublicHoliday.objects.filter(date__gte=today.date()).order_by('date')[:5]

        context = {
            'employee': employee,
            'attendance_count': attendance_count,
            'pending_leaves_count': pending_leaves_count,
            'total_leave_used': total_leave_used,
            'recent_leaves': recent_leaves,
            'leave_balances': leave_balances,
            'leave_balances': leave_balances,
            'upcoming_holidays': upcoming_holidays,
            'avg_daily_attendance': avg_daily_attendance,
        }
        return render(request, 'dashboard_ess.html', context)
