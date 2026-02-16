from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import PayrollBatch, AttendanceLog
from .services import PayrollService, BankTransferService
from .forms import AttendanceImportForm, AttendanceManualEntryForm
from django.utils import timezone
from django.contrib import messages

@login_required
def payroll_list(request):
    batches = PayrollBatch.objects.all().order_by('-month')
    return render(request, 'payroll/payroll_list.html', {'batches': batches})

@login_required
def payroll_detail(request, pk):
    from django.shortcuts import get_object_or_404
    batch = get_object_or_404(PayrollBatch, pk=pk)
    entries = batch.entries.select_related('employee').all()
    return render(request, 'payroll/payroll_detail.html', {'batch': batch, 'entries': entries})

from django.contrib.auth import get_user_model

@login_required
def attendance_list(request):
    from django.db.models import Q
    User = get_user_model()
    # Filter logs to show only Active employees
    logs = AttendanceLog.objects.select_related('employee').filter(employee__is_active=True).exclude(employee__status='ARCHIVED').exclude(employee__role='CEO')
    
    # SECURITY: Regular employees should ONLY see their own logs
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        logs = logs.filter(employee=request.user)
        
    logs = logs.order_by('-date')
    
    # Filters
    search_query = request.GET.get('search', '').strip()
    date_filter = None
    
    if search_query:
        # Check if search query is a date
        from datetime import datetime
        try:
            # Try YYYY-MM-DD
            date_filter = datetime.strptime(search_query, '%Y-%m-%d').date()
            logs = logs.filter(date=date_filter)
        except ValueError:
            # Not a date, search by name/ID
            search_id = search_query.replace('EMP-', '').replace('emp-', '')
            logs = logs.filter(
                Q(employee__full_name__icontains=search_query) |
                Q(employee__username__icontains=search_query) |
                Q(employee__employee_id__icontains=search_query) |
                Q(employee__id__icontains=search_id)
            )
        
    status_filter = request.GET.get('status', '')
    if status_filter == 'present':
        # "Present Only" should mean they actually clocked in/worked
        logs = logs.filter(Q(status='Present') | Q(total_work_minutes__gt=0))
    elif status_filter == 'absent':
        # "Absent Only" should show explicit absences
        logs = logs.filter(Q(status='Absent') | Q(is_absent=True))
    elif status_filter == 'weeklyoff':
        logs = logs.filter(status='WeeklyOff')
    elif status_filter == 'holiday':
        logs = logs.filter(status='Holiday')

    # Date Range Filter
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str:
        from datetime import datetime
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logs = logs.filter(date__gte=start_date)
        except ValueError:
            pass
            
    if end_date_str:
        from datetime import datetime
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            logs = logs.filter(date__lte=end_date)
        except ValueError:
            pass

    return render(request, 'payroll/attendance_list.html', {
        'logs': logs,
        'search_query': search_query,
        'status_filter': status_filter,
        'start_date': start_date_str,
        'end_date': end_date_str
    })

@login_required
def clear_attendance_logs(request):
    # Statistics for the dashboard
    if request.method == "POST":
        if request.user.is_staff or request.user.is_admin() or request.user.is_ceo():
            today = timezone.localdate()
            count, _ = AttendanceLog.objects.all().delete()
            messages.success(request, f"Cleared {count} attendance logs.")
        else:
            messages.error(request, "Permission denied.")
    return redirect('attendance_list')

@login_required
def attendance_import(request):
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = AttendanceImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            try:
                count = 0
                errors = []
                if uploaded_file.name.endswith('.csv'):
                    PayrollService.import_attendance_csv(uploaded_file, timezone.now().date())
                    count = 1 # approximate
                elif uploaded_file.name.endswith('.xlsx') or uploaded_file.name.endswith('.xls'):
                    count, errors, min_d, max_d = PayrollService.import_attendance_excel(uploaded_file)
                else:
                    messages.error(request, "File must be CSV or Excel (.xlsx or .xls).")
                    return redirect('attendance_import')
                
                if count > 0:
                    # Log to audit trail
                    from core.models import AuditLog
                    AuditLog.log(
                        user=request.user,
                        action=AuditLog.Action.IMPORT,
                        module=AuditLog.Module.ATTENDANCE,
                        object_repr=f"{count} records",
                        request=request
                    )
                    date_msg = ""
                    if min_d and max_d:
                         date_msg = f" Covering {min_d.strftime('%d-%b-%Y')} to {max_d.strftime('%d-%b-%Y')}."
                    messages.success(request, f"Attendance imported successfully. {count} logs created.{date_msg} Please ensure your date filter includes these dates.")
                elif errors:
                    # Show first 5 errors
                    error_msg = "Import failed. Errors: <br>" + "<br>".join(errors[:5])
                    if len(errors) > 5:
                         error_msg += f"<br>...and {len(errors) - 5} more."
                    messages.warning(request, error_msg, extra_tags='safe')
                else:
                    messages.warning(request, "Attendance imported but 0 logs were created. Check column headers and employee codes.")
                    
                return redirect('attendance_list')
            except Exception as e:
                messages.error(request, f"Error importing: {str(e)}")
    else:
        form = AttendanceImportForm()
    
    return render(request, 'payroll/attendance_form.html', {'form': form})

@login_required
def run_payroll_action(request):
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    if request.method == "POST":
        payroll_month_sel = request.POST.get('payroll_month_select')
        payroll_year_sel = request.POST.get('payroll_year_select')
        payroll_month_str = request.POST.get('payroll_month') # Legacy backup
        
        today = timezone.now().date()
        
        if payroll_month_sel and payroll_year_sel:
            try:
                year = int(payroll_year_sel)
                month = int(payroll_month_sel)
                batch_date = today.replace(year=year, month=month, day=1)
            except ValueError:
                messages.error(request, "Invalid month/year selection.")
                return redirect('payroll_list')
        elif payroll_month_str:
            try:
                # Parse "YYYY-MM"
                year, month = map(int, payroll_month_str.split('-'))
                batch_date = today.replace(year=year, month=month, day=1)
            except ValueError:
                messages.error(request, "Invalid month format selected.")
                return redirect('payroll_list')
        else:
            # Default to current month if nothing selected (though required in frontend)
            batch_date = today.replace(day=1)
        
        if PayrollBatch.objects.filter(month=batch_date).exists():
            messages.warning(request, f"Payroll for {batch_date.strftime('%B %Y')} already exists.")
            return redirect('payroll_list')

        batch = PayrollBatch.objects.create(month=batch_date)
        PayrollService.calculate_payroll(batch)
        
        file_content = BankTransferService.generate_export_file(batch)
        from django.core.files.base import ContentFile
        batch.sif_file.save(f"BankTransfer_{batch_date.strftime('%Y%m')}.csv", ContentFile(file_content))
        batch.status = PayrollBatch.Status.FINALIZED
        batch.save()
        
        from core.models import AuditLog
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            obj=batch,
            request=request,
            module=AuditLog.Module.PAYROLL
        )
        
        messages.success(request, f"Payroll generated successfully for {batch_date.strftime('%B %Y')}!")
        return redirect('payroll_list')
    
    return redirect('payroll_list')

@login_required
def my_payslips(request):
    employee = request.user
        
    # Get all payroll entries for this employee
    from .models import PayrollEntry
    payslips = PayrollEntry.objects.filter(employee=employee).select_related('batch').order_by('-batch__month')
    
    return render(request, 'payroll/my_payslips.html', {'payslips': payslips})

@login_required
def my_attendance(request):
    employee = request.user
    
    # Base Query
    logs = AttendanceLog.objects.filter(employee=employee).order_by('-date')
    
    # Date Filtering
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date:
        logs = logs.filter(date__gte=start_date)
        
    if end_date:
        logs = logs.filter(date__lte=end_date)
        
    # Default: Show current month if no filter
    if not start_date and not end_date:
        today = timezone.now().date()
        logs = logs.filter(date__month=today.month, date__year=today.year)

    return render(request, 'payroll/my_attendance.html', {
        'logs': logs,
        'start_date': start_date,
        'end_date': end_date
    })

@login_required
def gratuity_report(request):
    if not request.user.is_staff and not request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO']:
        return redirect('dashboard')
        
    from django.contrib.auth import get_user_model
    User = get_user_model()
    from datetime import date
    
    employees = User.objects.filter(role='EMPLOYEE', status='ACTIVE')
    report_data = []
    total_liability = 0
    
    today = date.today()
    
    for emp in employees:
        if not emp.date_of_joining:
            continue
            
        # Calculate Tenure
        delta = today - emp.date_of_joining
        years_service = delta.days / 365.25
        
        # Calculate Gratuity (Indian Standard: 15 days per year based on (Basic/26))
        if years_service < 4.8:
            gratuity_amount = 0
            gratuity_days = 0
        else:
            daily_basis = float(emp.salary_basic) / 26 if emp.salary_basic else 0
            gratuity_days = years_service * 15
            gratuity_amount = gratuity_days * daily_basis
        
        report_data.append({
            'employee': emp,
            'joining_date': emp.date_of_joining,
            'years_service': round(years_service, 2),
            'gratuity_amount': round(gratuity_amount, 2),
            'daily_basic': round(float(emp.salary_basic)/30, 2) if emp.salary_basic else 0
        })
        total_liability += gratuity_amount

    return render(request, 'payroll/gratuity_report.html', {
        'report_data': report_data,
        'total_liability': round(total_liability, 2),
        'today': today
    })

@login_required
def attendance_manual_entry(request):
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
         messages.error(request, "Permission denied.")
         return redirect('dashboard')

    if request.method == 'POST':
        form = AttendanceManualEntryForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.entry_type = AttendanceLog.EntryType.MANUAL
            log.save()
            
            from core.models import AuditLog
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                obj=log,
                request=request,
                module=AuditLog.Module.ATTENDANCE,
                object_repr=f"Attendance for {log.employee}"
            )
            
            messages.success(request, "Attendance manually logged successfully.")
            return redirect('attendance_list')
    else:
        form = AttendanceManualEntryForm()
    
    return render(request, 'payroll/manual_entry.html', {'form': form})

@login_required
def employee_autocomplete(request):
    """API endpoint for employee name autocomplete"""
    from django.http import JsonResponse
    from django.db.models import Q
    from django.contrib.auth import get_user_model
    
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'suggestions': []})
    
    User = get_user_model()
    
    # Search active employees only
    # We use a trick to prioritize matches that START with the query
    employees = User.objects.filter(
        Q(full_name__icontains=query) | 
        Q(username__icontains=query) |
        Q(aadhaar_number__icontains=query)
    ).filter(
        is_active=True
    ).exclude(
        status='ARCHIVED'
    ).exclude(role='CEO')
    
    # Sort in memory or keep it simple with icontains for now but filter in loop
    # Actually, let's just use istartswith for primary and icontains for secondary
    
    results = list(employees.filter(full_name__istartswith=query)[:10])
    if len(results) < 10:
        remaining = employees.exclude(id__in=[e.id for e in results])[:10 - len(results)]
        results.extend(list(remaining))
    
    suggestions = []
    for emp in results:
        display_id = emp.employee_id if emp.employee_id else f"EMP-{str(emp.id).zfill(3)}"
        suggestions.append({
            'id': emp.id,
            'name': emp.full_name or emp.username,
            'employee_id': display_id,
            'username': emp.username,
            'display': emp.full_name or emp.username
        })
    
    return JsonResponse({'suggestions': suggestions})
@login_required
def payroll_batch_delete(request, pk):
    from django.shortcuts import get_object_or_404
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        messages.error(request, "Permission denied.")
        return redirect('payroll_list')
        
    batch = get_object_or_404(PayrollBatch, pk=pk)
    
    if batch.status not in [PayrollBatch.Status.DRAFT, PayrollBatch.Status.VOID]:
        messages.error(request, "Only Draft or Void payroll batches can be deleted.")
        return redirect('payroll_list')
        
    if request.method == 'POST':
        batch.delete()
        messages.success(request, "Payroll batch deleted.")
        
    return redirect('payroll_list')

@login_required
def payroll_batch_void(request, pk):
    from django.shortcuts import get_object_or_404
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        messages.error(request, "Permission denied.")
        return redirect('payroll_list')
        
    batch = get_object_or_404(PayrollBatch, pk=pk)
    
    
    if request.method == 'POST':
        batch.status = PayrollBatch.Status.VOID
        batch.save()
        messages.warning(request, f"Payroll batch for {batch.month.strftime('%B %Y')} has been voided.")
        
    return redirect('payroll_list')

@login_required
def payslip_detail(request, pk):
    from django.shortcuts import get_object_or_404
    from .models import PayrollEntry
    entry = get_object_or_404(PayrollEntry, pk=pk)
    
    # Check permissions: Own or Admin
    if request.user != entry.employee and not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    return render(request, 'payroll/payslip.html', {'entry': entry})

@login_required
def manage_overtime(request):
    """
    Manager view to approve overtime minutes.
    Shows worked hours, calculated extra time, and approved OT field.
    """
    is_manager = hasattr(request.user, 'role') and request.user.role == 'PROJECT_MANAGER'
    allowed_roles = ['ADMIN', 'HR_MANAGER', 'CEO', 'PROJECT_MANAGER']
    
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in allowed_roles)):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
    
    from datetime import datetime, date
    from django.db.models import Q
    from django.utils import timezone
    
    # 1. Date Filter
    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    try:
        year, month = map(int, month_str.split('-'))
        start_date = date(year, month, 1)
    except ValueError:
        start_date = timezone.now().date().replace(day=1)
        month_str = start_date.strftime('%Y-%m')

    # 2. Base Query
    logs = AttendanceLog.objects.filter(
        date__year=start_date.year, 
        date__month=start_date.month
    ).select_related('employee').order_by('-date', 'employee__full_name')

    # 2b. Role-based Filtering (Strict Assignment for Managers)
    if is_manager and not (request.user.is_superuser or request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO']):
        # Show only subordinates
        # 'employee__managers' is the reverse lookup for "Employees who have this user as manager"
        logs = logs.filter(employee__managers=request.user)

    # Calculate Total OT ( Approved )
    from django.db.models import Sum
    total_approved_ot = logs.aggregate(Sum('approved_overtime_minutes'))['approved_overtime_minutes__sum'] or 0
    total_ot_hours = round(total_approved_ot / 60, 1)
    
    # 3. Search Filter
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # Search by name or ID
        logs = logs.filter(
            Q(employee__full_name__icontains=search_query) |
            Q(employee__username__icontains=search_query) |
            Q(employee__employee_id__icontains=search_query)
        )

    # 4. Handle POST (Bulk Update via Checkboxes)
    if request.method == "POST":
        visible_log_ids = request.POST.getlist('log_ids')
        checked_ids = set()
        
        # Collect checked IDs
        for key in request.POST.keys():
            if key.startswith('ot_check_'):
                try:
                    log_id = int(key.replace('ot_check_', ''))
                    checked_ids.add(log_id)
                except ValueError:
                    continue
        
        updated_count = 0
        if visible_log_ids:
            # Fetch logs that are candidates for update (not locked)
            # Apply same permission filter effectively by checking against 'logs' queryset logic or just ID
            # But simpler: logs_to_update = AttendanceLog.objects.filter(id__in=visible_log_ids, is_locked=False)
            # If a malicious manager tries to update a non-subordinate log ID, they shouldn't be able to.
            # So we should scope it.
            
            scope = AttendanceLog.objects.all()
            if is_manager and not (request.user.is_superuser or request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO']):
                 scope = scope.filter(employee__managers=request.user)
            
            logs_to_update = scope.filter(id__in=visible_log_ids, is_locked=False)
            
            for log in logs_to_update:
                is_checked = log.id in checked_ids
                
                # Default: 0
                new_approved_minutes = 0
                
                if is_checked:
                    # If checked, set to calculated extra time
                    # Rule: OT is time worked beyond 8 hours (480 mins)
                    extra_minutes = max(0, log.total_work_minutes - 480)
                    new_approved_minutes = extra_minutes
                
                if log.approved_overtime_minutes != new_approved_minutes:
                    log.approved_overtime_minutes = new_approved_minutes
                    log.save(update_fields=['approved_overtime_minutes'])
                    updated_count += 1
        
        if updated_count > 0:
            messages.success(request, f"Successfully updated overtime for {updated_count} records.")
        else:
            messages.info(request, "No changes detected.")
            
        return redirect(f"{request.path}?month={month_str}&search={search_query}")

    return render(request, 'payroll/manage_ot.html', {
        'logs': logs,
        'selected_month': month_str,
        'search_query': search_query,
        'total_ot_hours': total_ot_hours,
        'total_staff': logs.values('employee').distinct().count()
    })

