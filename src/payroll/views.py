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
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, batches, default_limit=10)
    
    return render(request, 'payroll/payroll_list.html', {
        'batches': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True
    })

@login_required
def payroll_detail(request, pk):
    from django.shortcuts import get_object_or_404
    from django.db.models import Sum
    batch = get_object_or_404(PayrollBatch, pk=pk)
    entries = batch.entries.select_related('employee').all()
    
    # Calculate stats for the summary cards
    totals = entries.aggregate(
        total_net=Sum('net_salary'),
        total_deductions=Sum('deductions'),
        total_ot=Sum('ot_pay')
    )
    
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, entries, default_limit=10)

    return render(request, 'payroll/payroll_detail.html', {
        'batch': batch, 
        'entries': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'total_net': totals['total_net'] or 0,
        'total_deductions': totals['total_deductions'] or 0,
        'total_ot': totals['total_ot'] or 0
    })

from django.contrib.auth import get_user_model

@login_required
def attendance_list(request):
    from django.db.models import Q
    User = get_user_model()
    # Filter logs to show only Active employees
    logs = AttendanceLog.objects.select_related('employee').filter(employee__is_active=True).exclude(employee__is_staff=True).exclude(employee__status='ARCHIVED').exclude(employee__role__iexact='CEO').exclude(employee__role__iexact='ADMIN')
    
    # Handle Manual Entry / Manual Punch Form Submissions
    manual_entry_form = None
    manual_punch_req_form = None
    
    if request.method == 'POST':
        if 'manual_entry_submit' in request.POST:
            if request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO']):
                manual_entry_form = AttendanceManualEntryForm(request.POST)
                if manual_entry_form.is_valid():
                    employee = manual_entry_form.cleaned_data['employee']
                    date = manual_entry_form.cleaned_data['date']
                    # Delete existing log BEFORE save so unique_together doesn't block
                    deleted_count, _ = AttendanceLog.objects.filter(employee=employee, date=date).delete()
                    log = manual_entry_form.save(commit=False)
                    log.entry_type = AttendanceLog.EntryType.MANUAL
                    log.save()
                    if deleted_count > 0:
                        messages.success(request, f"Manual punch saved — previous log for {employee} on {date} was overridden.")
                    else:
                        messages.success(request, "Attendance manually logged successfully.")
                    return redirect('attendance_list')
                else:
                    messages.error(request, "Please correct the errors in the manual entry form.")
            else:
                messages.error(request, "Permission denied.")
        
        elif 'manual_punch_submit' in request.POST:
            manual_punch_req_form = ManualPunchRequestForm(request.POST, user=request.user)
            if manual_punch_req_form.is_valid():
                punch_req = manual_punch_req_form.save(commit=False)
                punch_req.employee = request.user
                punch_req.status = 'PENDING'
                
                # Check for physical overlap
                overlap = False
                existing_log = AttendanceLog.objects.filter(employee=request.user, date=punch_req.date).first()
                if existing_log and existing_log.segments:
                    for s in existing_log.segments:
                        if punch_req.punch_in_time < s['out'] and punch_req.punch_out_time > s['in']:
                            overlap = True; break
                
                if overlap:
                    messages.error(request, f"Overlapping hours! The requested time conflicts with an existing physical punch for {punch_req.date}.")
                    return redirect('attendance_list')
                    
                # Check for overlap with other manual requests
                if ManualPunchRequest.objects.filter(
                    employee=request.user, date=punch_req.date, status__in=['PENDING', 'APPROVED'],
                    punch_in_time__lt=punch_req.punch_out_time, punch_out_time__gt=punch_req.punch_in_time
                ).exists():
                    messages.error(request, "This time range overlaps with another pending or approved manual request.")
                    return redirect('attendance_list')
                
                punch_req.save()
                messages.success(request, "Manual punch request submitted for approval.")
                return redirect('attendance_list')
            else:
                messages.error(request, "Please correct the errors in your punch request.")
            
    if manual_entry_form is None:
        manual_entry_form = AttendanceManualEntryForm()
    if manual_punch_req_form is None:
        manual_punch_req_form = ManualPunchRequestForm(user=request.user)
    
    # SECURITY: Regular employees should ONLY see their own logs
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO'])):
        logs = logs.filter(employee=request.user)
        
    logs = logs.order_by('-date')
    
    # Filters
    search_query = request.GET.get('search', '').strip()
    emp_pk = request.GET.get('employee_id')
    date_filter = None
    
    if emp_pk:
        logs = logs.filter(employee_id=emp_pk)

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
                Q(employee__id__exact=search_id if search_id.isdigit() else -1)
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
    
    view_start_date = None
    view_end_date = None

    if start_date_str:
        from datetime import datetime
        try:
            view_start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logs = logs.filter(date__gte=view_start_date)
        except ValueError:
            pass
            
    if end_date_str:
        from datetime import datetime
        try:
            view_end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            logs = logs.filter(date__lte=view_end_date)
        except ValueError:
            pass

    # --- ADVANCED: Full Log Reconstruction (For "Summary" drill-down) ---
    # If viewing a specific employee for a specific month, fill in the "Missing" days (Absences/Weekends)
    if request.GET.get('from') == 'summary' and view_start_date and view_end_date and (search_query or emp_pk):
        # Try to identify which employee we are looking at precisely
        # (We use the filtered logs or re-query if logs are empty)
        target_employee = None
        
        if emp_pk:
            target_employee = User.objects.filter(id=emp_pk).first()
        
        if not target_employee:
            if logs.exists():
                # Check if all logs are for the same employee
                emp_ids = logs.values_list('employee_id', flat=True).distinct()
                if emp_ids.count() == 1:
                    target_employee = User.objects.get(id=emp_ids[0])
            
            if not target_employee and search_query:
                # Try to resolve employee from search query if no logs found
                search_id = search_query.replace('EMP-', '').replace('emp-', '')
                emp_match = User.objects.filter(
                    Q(full_name__iexact=search_query) |
                    Q(username__iexact=search_query) |
                    Q(employee_id__iexact=search_query) |
                    Q(id=search_id if search_id.isdigit() else -1)
                ).first()
                if emp_match:
                    target_employee = emp_match

        if target_employee:
            # We have a specific employee! Let's build a day-by-day log list.
            from datetime import timedelta
            from core.models import CompanySettings
            from leaves.models import LeaveRequest
            import calendar
            
            settings = CompanySettings.load()
            full_logs = []
            
            # Map existing logs by date for quick access
            log_map = {log.date: log for log in logs}
            
            curr = view_start_date
            while curr <= view_end_date:
                if curr in log_map:
                    full_logs.append(log_map[curr])
                else:
                    # Create a "Virtual" log for this date
                    virtual_status = "Absent"
                    is_holiday_flag = False
                    is_absent_flag = True
                    is_compliant_flag = False
                    
                    if settings.is_holiday(curr):
                        # Determine if it's a WeeklyOff or a Holiday
                        # (is_holiday returns True for both)
                        if curr.weekday() == 6: # Sunday
                             virtual_status = "WeeklyOff"
                        elif settings.second_saturday_holiday and curr.weekday() == 5:
                             # Check if it's 2nd Saturday
                             month_calendar = calendar.monthcalendar(curr.year, curr.month)
                             saturdays = [row[calendar.SATURDAY] for row in month_calendar if row[calendar.SATURDAY] != 0]
                             if len(saturdays) > 1 and curr.day == saturdays[1]:
                                 virtual_status = "WeeklyOff"
                             else:
                                 virtual_status = "Holiday"
                        else:
                             virtual_status = "Holiday"
                        
                        is_holiday_flag = True
                        is_absent_flag = False
                    else:
                        # Check if they are on APPROVED Leave this day
                        has_leave = LeaveRequest.objects.filter(
                            employee=target_employee,
                            status__in=['MGR_APPROVED', 'HR_PROCESSED', 'APPROVED'],
                            start_date__lte=curr,
                            end_date__gte=curr
                        ).exists()
                        if has_leave:
                            virtual_status = "Leave"
                            is_absent_flag = False
                    
                    v_log = AttendanceLog(
                        employee=target_employee,
                        date=curr,
                        status=virtual_status,
                        is_absent=is_absent_flag,
                        is_compliant=False,
                        total_work_minutes=0
                    )
                    full_logs.append(v_log)
                curr += timedelta(days=1)
            
            # Sort reversed to match original behavior
            logs = sorted(full_logs, key=lambda x: x.date, reverse=True)

    # Pending requests count for manager badge
    pending_count = 0
    if request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO']):
        pending_count = ManualPunchRequest.objects.filter(status='PENDING').count()

    # Calculate real log count (excluding virtual ones)
    real_log_count = 0
    reconstructed_count = 0
    if isinstance(logs, list):
        real_log_count = sum(1 for log in logs if log.pk)
        reconstructed_count = len(logs) - real_log_count
    else:
        real_log_count = logs.count()

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, logs, default_limit=20)
    
    return render(request, 'payroll/attendance_list.html', {
        'logs': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'real_log_count': real_log_count,
        'reconstructed_count': reconstructed_count,
        'search_query': search_query,
        'status_filter': status_filter,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'manual_entry_form': manual_entry_form,
        'manual_punch_req_form': manual_punch_req_form,
        'pending_count': pending_count
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
        
        messages.success(request, f"Payroll generated successfully for {batch_date.strftime('%B %Y')}!")
        return redirect('payroll_list')
    
    return redirect('payroll_list')

@login_required
def my_payslips(request):
    employee = request.user
        
    # Get all payroll entries for this employee
    from .models import PayrollEntry
    payslips = PayrollEntry.objects.filter(employee=employee).select_related('batch').order_by('-batch__month')
    
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, payslips, default_limit=10)
    
    return render(request, 'payroll/my_payslips.html', {
        'payslips': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True
    })

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

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, logs, default_limit=20)

    return render(request, 'payroll/my_attendance.html', {
        'logs': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
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
    
    employees = User.objects.filter(role__iexact='EMPLOYEE', status='ACTIVE')
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

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, report_data, default_limit=10)

    return render(request, 'payroll/gratuity_report.html', {
        'report_data': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
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
            employee = form.cleaned_data['employee']
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            # determine reason text to save
            reason_type = form.cleaned_data.get('reason_type')
            custom_remarks = form.cleaned_data.get('remarks')
            final_remarks = custom_remarks if reason_type == 'Other' else reason_type
            
            work_duration_hours = form.cleaned_data.get('work_duration', 8.0)
            work_minutes = int(float(work_duration_hours) * 60)
            
            from datetime import timedelta
            current_date = start_date
            
            logs_created = 0
            while current_date <= end_date:
                AttendanceLog.objects.filter(employee=employee, date=current_date).delete()
                
                log = AttendanceLog(
                    employee=employee,
                    date=current_date,
                    status=AttendanceLog.Status.PRESENT,
                    is_compliant=True,  # Assume manual entry is compliant
                    total_work_minutes=work_minutes,
                    remarks=final_remarks,
                    entry_type=AttendanceLog.EntryType.MANUAL
                )
                
                log.save()
                
                current_date += timedelta(days=1)
                logs_created += 1

            messages.success(request, f"Successfully logged attendance for {logs_created} day(s). Existing entries overridden.")
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
    ).exclude(is_staff=True).exclude(role__iexact='CEO').exclude(role__iexact='ADMIN')
    
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
        from django.db import transaction
        from leaves.models import LOPAdjustment, LeaveType, LeaveBalance
        
        with transaction.atomic():
            # Restore Annual Leave balances for any approved LOP adjustments
            # before cascade-deleting the batch and its entries
            approved_adjustments = LOPAdjustment.objects.filter(
                payroll_entry__batch=batch,
                status=LOPAdjustment.Status.APPROVED
            ).select_related('employee')
            
            for adj in approved_adjustments:
                try:
                    ann_type = LeaveType.objects.get(code='ANN')
                    balance = LeaveBalance.objects.filter(
                        employee=adj.employee,
                        leave_type=ann_type,
                        year=adj.created_at.year
                    ).first()
                    if balance:
                        balance.days_used = max(0.0, float(balance.days_used) - float(adj.requested_annual_leave_days))
                        balance.save()
                except LeaveType.DoesNotExist:
                    pass
            
            batch.delete()
        
        messages.success(request, "Payroll batch deleted and leave balances restored.")
        
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

    # 2. Base Query (Filter out inactive/archived employees)
    logs = AttendanceLog.objects.filter(
        date__year=start_date.year, 
        date__month=start_date.month,
        employee__is_active=True
    ).exclude(employee__status='ARCHIVED').select_related('employee').order_by('-date', 'employee__full_name')

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

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, logs, default_limit=10)

    return render(request, 'payroll/manage_ot.html', {
        'logs': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'selected_month': month_str,
        'search_query': search_query,
        'total_ot_hours': total_ot_hours,
        'total_staff': logs.values('employee').distinct().count()
    })

@login_required
def attendance_summary(request):
    """
    Monthly Attendance Summary Report Page
    """
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO', 'PROJECT_MANAGER'])):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')

    from datetime import date
    from django.utils import timezone
    
    # 1. Date Selection Logic
    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    try:
        # Expected format YYYY-MM
        year, month = map(int, month_str.split('-'))
        report_date = date(year, month, 1)
    except (ValueError, AttributeError):
        report_date = timezone.now().date().replace(day=1)
        month_str = report_date.strftime('%Y-%m')

    # 2. Fetch Aggregated Report Data
    report_data = PayrollService.get_monthly_attendance_report(report_date)
    
    # 3. Handle Searching
    search_query = request.GET.get('q', '').strip()
    if search_query:
        query_lower = search_query.lower()
        filtered_data = []
        for row in report_data:
            emp = row['employee']
            full_name = (emp.full_name or "").lower()
            username = (emp.username or "").lower()
            emp_id = (emp.employee_id or "").lower()
            
            if query_lower in full_name or query_lower in username or query_lower in emp_id:
                filtered_data.append(row)
        report_data = filtered_data

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, report_data, default_limit=10)

    return render(request, 'payroll/attendance_summary.html', {
        'report_data': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'selected_month': month_str,
        'report_date': report_date,
        'search_query': search_query,
        'threshold': 8.0 # Threshold for average hours highlight
    })

from .forms import ManualPunchRequestForm
from .models import ManualPunchRequest

@login_required
def my_manual_punches(request):
    """
    Employee view to list their own manual punch requests.
    """
    requests_list = ManualPunchRequest.objects.filter(employee=request.user).order_by('-created_at')
    
    if request.method == 'POST' and 'manual_punch_submit' in request.POST:
        manual_punch_req_form = ManualPunchRequestForm(request.POST, user=request.user)
        if manual_punch_req_form.is_valid():
            punch_req = manual_punch_req_form.save(commit=False)
            punch_req.employee = request.user
            punch_req.status = 'PENDING'
            
            # Check for physical overlap
            overlap = False
            existing_log = AttendanceLog.objects.filter(employee=request.user, date=punch_req.date).first()
            if existing_log and existing_log.segments:
                for s in existing_log.segments:
                    if punch_req.punch_in_time < s['out'] and punch_req.punch_out_time > s['in']:
                        overlap = True; break
            
            if overlap:
                messages.error(request, f"Overlapping hours! The requested time conflicts with an existing physical punch for {punch_req.date}.")
                return redirect('my_manual_punches')
                
            # Check for overlap with other manual requests
            if ManualPunchRequest.objects.filter(
                employee=request.user, date=punch_req.date, status__in=['PENDING', 'APPROVED'],
                punch_in_time__lt=punch_req.punch_out_time, punch_out_time__gt=punch_req.punch_in_time
            ).exists():
                messages.error(request, "This time range overlaps with another pending or approved manual request.")
                return redirect('my_manual_punches')
            
            punch_req.save()
            messages.success(request, "Manual punch request submitted for approval.")
            return redirect('my_manual_punches')
        else:
            messages.error(request, "Please correct the errors in your punch request.")
    else:
        manual_punch_req_form = ManualPunchRequestForm(user=request.user)
    
    return render(request, 'payroll/my_manual_punches.html', {
        'requests': requests_list,
        'manual_punch_req_form': manual_punch_req_form
    })

@login_required
def manual_punch_request(request):
    """
    Handles employee submission of a manual punch request.
    """
    if request.method == 'POST':
        form = ManualPunchRequestForm(request.POST, user=request.user)
        referer = request.META.get('HTTP_REFERER', 'attendance_list')
        if form.is_valid():
            punch_req = form.save(commit=False)
            punch_req.employee = request.user
            punch_req.status = 'PENDING'
            
            # Check for physical overlap
            overlap = False
            existing_log = AttendanceLog.objects.filter(employee=request.user, date=punch_req.date).first()
            if existing_log and existing_log.segments:
                for s in existing_log.segments:
                    if punch_req.punch_in_time < s['out'] and punch_req.punch_out_time > s['in']:
                        overlap = True; break
            
            if overlap:
                messages.error(request, f"Overlapping hours! The requested time conflicts with an existing physical punch for {punch_req.date}.")
                return redirect(referer)
                
            # Check for overlap with other manual requests
            if ManualPunchRequest.objects.filter(
                employee=request.user, date=punch_req.date, status__in=['PENDING', 'APPROVED'],
                punch_in_time__lt=punch_req.punch_out_time, punch_out_time__gt=punch_req.punch_in_time
            ).exists():
                messages.error(request, "This time range overlaps with another pending or approved manual request.")
                return redirect(referer)
            
            punch_req.save()
            messages.success(request, "Manual punch request submitted for approval.")
            return redirect(referer)
        else:
            messages.error(request, "Please correct the errors in your punch request.")
            return redirect(referer)
    return redirect('attendance_list')

@login_required
def manual_punch_approvals(request):
    """
    Manager view to list PENDING manual punch requests.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO', 'PROJECT_MANAGER'])):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    pending_requests = ManualPunchRequest.objects.filter(
        status='PENDING', employee__is_active=True
    ).exclude(employee__status='ARCHIVED').select_related('employee').order_by('-created_at')
    
    # Filter to only show requests for subordinates if user is essentially a project manager
    if not (request.user.is_staff or getattr(request.user, 'role', '') in ['ADMIN', 'CEO', 'HR_MANAGER']):
        pending_requests = pending_requests.filter(employee__managers=request.user)
    
    return render(request, 'payroll/manual_punch_approvals.html', {
        'pending_requests': pending_requests
    })

@login_required
def manual_punch_action(request, pk):
    """
    Manager action to APPROVE or REJECT a request.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'role') and request.user.role in ['ADMIN', 'HR_MANAGER', 'CEO', 'PROJECT_MANAGER'])):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    action = request.POST.get('action') # 'APPROVE' or 'REJECT'
    if request.method == 'POST' and action in ['APPROVE', 'REJECT']:
        try:
            from django.shortcuts import get_object_or_404
            punch_req = get_object_or_404(ManualPunchRequest, pk=pk)
            
            # Authorization check: Is the user an admin/CEO, or are they an assigned manager?
            is_authorized = False
            if request.user.is_staff or getattr(request.user, 'role', '') in ['ADMIN', 'CEO', 'HR_MANAGER']:
                is_authorized = True
            elif punch_req.employee.managers.filter(id=request.user.id).exists():
                is_authorized = True
                
            if not is_authorized:
                messages.error(request, "Permission denied. Only assigned managers can process this request.")
                return redirect('manual_punch_approvals')

            punch_req = PayrollService.process_manual_punch_approval(pk, request.user, action)
            if action == 'APPROVE':
                messages.success(request, f"Request for {punch_req.employee.full_name} APPROVED and attendance updated.")
            else:
                messages.info(request, f"Request for {punch_req.employee.full_name} REJECTED.")
        except Exception as e:
            messages.error(request, f"Error processing request: {str(e)}")
            
    return redirect('manual_punch_approvals')
