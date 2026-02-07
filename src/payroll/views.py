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
    search_query = request.GET.get('search', '')
    if search_query:
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

    date_str = request.GET.get('date')
    if date_str:
        from datetime import datetime
        valid_date = None
        # Try various formats
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
            try:
                valid_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        
        if valid_date:
            logs = logs.filter(date=valid_date)
        
    return render(request, 'payroll/attendance_list.html', {
        'logs': logs,
        'search_query': search_query,
        'status_filter': status_filter,
        'selected_date': date_str
    })

@login_required
def clear_attendance_logs(request):
    if request.method == "POST":
        if request.user.is_staff or request.user.role in ['ADMIN', 'CEO']:
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
                    count, errors = PayrollService.import_attendance_excel(uploaded_file)
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
                    messages.success(request, f"Attendance imported successfully. {count} logs created.")
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
        today = timezone.now().date()
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
        
        messages.success(request, "Payroll generated successfully!")
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
    
    if batch.status != PayrollBatch.Status.DRAFT:
        messages.error(request, "Only Draft payroll batches can be deleted.")
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
        messages.warning(request, f"Payroll batch for {batch.month|date:'F Y'} has been voided.")
        
    return redirect('payroll_list')
