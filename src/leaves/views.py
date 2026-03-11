from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import LeaveRequest, LeaveType, LeaveBalance, LOPAdjustment
from .forms import LeaveRequestForm, LeaveTypeForm, LOPAdjustmentForm
from django.contrib import messages
from core.models import AuditLog
from django.db.models import Q
from payroll.models import PayrollEntry

@login_required
def leave_list(request):
    from django.db import models
    user = request.user
    is_admin = user.is_staff or user.is_admin() or user.is_hr() or user.is_ceo() or user.is_project_manager()
    
    import datetime
    current_year = datetime.date.today().year
    
    balances = []
    if not is_admin:
        from .models import LeaveBalance
        from django.utils import timezone
        today = timezone.localdate()
        
        valid_types = LeaveType.objects.filter(is_active=True)
        # Filter by gender if available
        if user.gender:
            valid_types = valid_types.filter(Q(eligibility_gender='ALL') | Q(eligibility_gender=user.gender))

        for lt in valid_types:
            total_quota = float(lt.days_entitlement)
            
            if getattr(lt, 'accrual_frequency', '') == 'MONTHLY':
                if getattr(lt, 'reset_monthly', False):
                    total_quota = total_quota / 12.0
                else:
                    total_quota = (total_quota / 12.0) * max(1, today.month)
            
            if lt.reset_monthly:
                 reqs = LeaveRequest.objects.filter(
                    employee=user, leave_type=lt, status__in=['APPROVED', 'HR_PROCESSED'],
                    start_date__month=today.month, start_date__year=today.year
                 )
                 used = sum(float(r.duration_days) for r in reqs) or 0.0
            else:
                 reqs = LeaveRequest.objects.filter(
                     employee=user, leave_type=lt, status__in=['APPROVED', 'HR_PROCESSED'],
                     start_date__year=today.year
                 )
                 used = sum(float(r.duration_days) for r in reqs) or 0.0
            
            balance_obj, created = LeaveBalance.objects.get_or_create(
                employee=user, leave_type=lt, year=current_year,
                defaults={'total_entitlement': total_quota, 'days_used': used}
            )
            
            should_save = False
            if float(balance_obj.total_entitlement) != total_quota:
                balance_obj.total_entitlement = total_quota
                should_save = True
            
            if float(balance_obj.days_used) != float(used):
                balance_obj.days_used = used
                should_save = True
            
            if should_save:
                balance_obj.save()
            
            # HIDDEN CHECK
            if lt.hidden_unless_used and float(balance_obj.days_used) <= 0:
                pass
            else:
                balances.append(balance_obj)


    # Permission Logic
    if user.is_superuser or user.is_admin() or user.is_ceo():
        # Admin / CEO sees ALL (except cancelled, and inactive employees)
        leaves = LeaveRequest.objects.filter(employee__is_active=True).exclude(employee__status='ARCHIVED').exclude(status='CANCELLED').order_by('-created_at')
        
    elif user.is_hr():
        # HR sees MGR_APPROVED (waiting for HR) + History + Own Requests (except cancelled)
        leaves = LeaveRequest.objects.filter(
            Q(status__in=['MGR_APPROVED', 'HR_PROCESSED', 'APPROVED', 'REJECTED']) | 
            Q(employee=user)
        ).filter(employee__is_active=True).exclude(employee__status='ARCHIVED').exclude(status='CANCELLED').order_by('-created_at')
        
    else:
        # Check PM logic
        is_pm = False
        if user.is_project_manager():
                is_pm = True
                
        if is_pm:
             # PM sees Assigned Requests + Own Requests (except cancelled)
            leaves = LeaveRequest.objects.filter(
                Q(assigned_manager=user) | Q(employee=user)
            ).filter(employee__is_active=True).exclude(employee__status='ARCHIVED').exclude(status='CANCELLED').order_by('-created_at')
        else:
             # Regular Employee (shows all their requests including cancelled)
            leaves = LeaveRequest.objects.filter(employee=user).order_by('-created_at')
             
    # Upcoming Meetings (Add-on for UI)
    from meetings.models import Meeting
    from django.utils import timezone
    # Show all meetings for today and future (include passed meetings of today)
    from datetime import datetime, time
    today_start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    
    upcoming_meetings = Meeting.objects.filter(
        Q(participants=user) | Q(organizer=user),
        start_time__gte=today_start
    ).distinct().order_by('start_time')[:5]

    # Check for convertible LOP (Employee only)
    has_lop_to_convert = False
    latest_lop_entry = None
    if not is_admin:
        latest_lop_entry = PayrollEntry.objects.filter(employee=request.user, shortfall_work_hours__gt=0).order_by('-created_at').first()
        if latest_lop_entry:
            # Also check if there isn't already a pending adjustment for this entry
            pending_adj = LOPAdjustment.objects.filter(payroll_entry=latest_lop_entry, status='PENDING').exists()
            if not pending_adj:
                # Also check that the employee has enough Annual Leave balance (at least 0.5 days)
                import math
                try:
                    from django.utils import timezone as tz
                    ann_type = LeaveType.objects.get(code='ANN')
                    al_bal = LeaveBalance.objects.filter(
                        employee=request.user, leave_type=ann_type, year=tz.now().year
                    ).first()
                    al_remaining = math.floor(float(al_bal.remaining) * 2) / 2.0 if al_bal else 0.0
                    if al_remaining >= 0.5:
                        has_lop_to_convert = True
                except LeaveType.DoesNotExist:
                    pass  # No AL leave type configured - button stays hidden

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, leaves, default_limit=10, unique_id='_leaves')

    return render(request, 'leaves/leave_list.html', {
        'leaves': page_obj, 
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'is_admin': is_admin, 
        'balances': balances,
        'upcoming_meetings': upcoming_meetings,
        'has_lop_to_convert': has_lop_to_convert,
        'latest_lop_entry': latest_lop_entry
    })
@login_required
def leave_create(request):
    # Eligibility Logic
    from django.utils import timezone
    from django.db import models
    from django.db.models import Q, Sum
    from .models import LeaveBalance
    from datetime import date
    
    today = timezone.localdate()
    current_year = today.year
    
    # 1. Calc Service Days & Gender
    gender = getattr(request.user, 'gender', 'Male') 
    service_days = 0
    if request.user.date_of_joining:
        service_days = (today - request.user.date_of_joining).days
        
    # 2. Filter Valid Leave Types (Explicit Active Check)
    valid_types = LeaveType.objects.filter(is_active=True, status='ACTIVE').filter(
        min_service_days__lte=service_days
    ).filter(
        Q(eligibility_gender='ALL') | Q(eligibility_gender=gender)
    )
    print(f"DEBUG: Found {valid_types.count()} active leave types for user {request.user.username}")
    
    # 3. Get Leave Balances for current year
    leave_balances = {}
    for lt in valid_types:
        total_quota = float(lt.days_entitlement)
        
        if getattr(lt, 'accrual_frequency', '') == 'MONTHLY':
            if getattr(lt, 'reset_monthly', False):
                total_quota = total_quota / 12.0
            else:
                total_quota = (total_quota / 12.0) * max(1, today.month)
                
        used = 0.0
        
        if lt.reset_monthly:
            reqs = LeaveRequest.objects.filter(
                employee=request.user, leave_type=lt, status__in=['APPROVED', 'HR_PROCESSED'],
                start_date__month=today.month, start_date__year=today.year
            )
            used = sum(float(r.duration_days) for r in reqs) or 0.0
        else:
            reqs = LeaveRequest.objects.filter(
                employee=request.user, leave_type=lt, status__in=['APPROVED', 'HR_PROCESSED'],
                start_date__year=current_year
            )
            used = sum(float(r.duration_days) for r in reqs) or 0.0

        balance, created = LeaveBalance.objects.get_or_create(
            employee=request.user, leave_type=lt, year=current_year,
            defaults={'total_entitlement': total_quota, 'days_used': used}
        )
        
        # Update if changed (Dynamic calculation)
        if float(balance.total_entitlement) != total_quota or float(balance.days_used) != float(used):
             balance.total_entitlement = total_quota
             balance.days_used = used
             balance.save()
        
        used = float(balance.days_used)
        total_quota = float(balance.total_entitlement)

        leave_balances[lt.id] = {
            'total': total_quota,
            'used': used,
            'remaining': max(0, total_quota - used)
        }

    if request.method == 'POST':
        import json
        form = LeaveRequestForm(request.POST, user=request.user)
        form.fields['leave_type'].queryset = valid_types
        
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = request.user
            
            # Auto-assign manager if not set (Crucial for approval workflow)
            if not leave.assigned_manager:
                manager = request.user.managers.first() # Get primary manager
                if manager:
                    leave.assigned_manager = manager
                else:
                    messages.error(request, "Submission Failed: You are not assigned to a Reporting Manager. Please contact HR to assign a manager.")
                    return redirect('leave_add') # Reload form to show error

            # Validate balance
            requested_days = leave.duration_days
            leave_type_id = leave.leave_type.id
            
            if leave_type_id in leave_balances:
                if leave.leave_type.allow_unlimited:
                    pass
                else:
                    remaining = leave_balances[leave_type_id]['remaining']
                    if requested_days > remaining:
                        messages.error(
                            request, 
                            f"Insufficient leave balance. You requested {requested_days} days but only have {remaining} days remaining for {leave.leave_type.name}."
                        )
                        return render(request, 'leaves/leave_form.html', {
                            'form': form,
                            'type_config': json.dumps({
                                lt.id: {
                                    'duration': (lt.duration_days or 0),
                                    'allow_half_day': lt.allow_half_day
                                } for lt in valid_types
                            }),
                            'unlimited_types': json.dumps([lt.id for lt in valid_types if lt.allow_unlimited]),
                            'unlimited_types_list': [lt.id for lt in valid_types if lt.allow_unlimited],
                            'leave_balances': leave_balances
                        })
            
            leave.save()
            
            messages.success(request, f"Leave request submitted for {requested_days} days.")
            return redirect('leave_list')
    else:
        form = LeaveRequestForm(user=request.user)
        form.fields['leave_type'].queryset = valid_types
    
    if not valid_types.exists():
        messages.warning(request, "You are not eligible for any leave types at this time (Service/Gender criteria).")

    # Prepare configuration for frontend (Duration handling)
    import json
    type_config = {
        lt.id: {
            'duration': (lt.duration_days or 0),
            'allow_half_day': lt.allow_half_day
        } for lt in valid_types
    }

    return render(request, 'leaves/leave_form.html', {
        'form': form, 
        'type_config': json.dumps(type_config),
        'unlimited_types': json.dumps([lt.id for lt in valid_types if lt.allow_unlimited]),
        'unlimited_types_list': [lt.id for lt in valid_types if lt.allow_unlimited],
        'leave_balances': leave_balances
    })

@login_required
def leave_delete(request, pk):
    """Allow employees to delete their own cancelled leave requests"""
    leave = get_object_or_404(LeaveRequest, pk=pk)
    
    # Permission check: only the employee who created it can delete
    if leave.employee != request.user:
        messages.error(request, "You don't have permission to delete this leave request.")
        return redirect('leave_list')
    
    # Only allow deletion of cancelled requests
    if leave.status != 'CANCELLED':
        messages.error(request, "Only cancelled leave requests can be deleted.")
        return redirect('leave_list')
    
    if request.method == 'POST':
        leave.delete()
        messages.success(request, "Cancelled leave request has been deleted.")
        return redirect('leave_list')
    
    return redirect('leave_list')


from .forms_ticket import TicketRequestForm
from .models import TicketRequest

@login_required
def ticket_list(request):
    user = request.user
    if user.is_staff or user.is_admin() or user.is_hr() or user.is_ceo(): # Management sees all
        tickets = TicketRequest.objects.all().order_by('-created_at')
    else: # Employee sees own
        if hasattr(user, 'employee_profile'):
            tickets = TicketRequest.objects.filter(employee=user.employee_profile).order_by('-created_at')
        else:
            tickets = TicketRequest.objects.none()
            
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, tickets, default_limit=10, unique_id='_tickets')
            
    return render(request, 'leaves/ticket_list.html', {
        'tickets': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True
    })

@login_required
def ticket_create(request):
    if request.user.is_admin() or request.user.is_ceo() or request.user.is_project_manager():
        messages.error(request, "Management roles cannot submit new ticket requests.")
        return redirect('ticket_list')

    if request.method == 'POST':
        form = TicketRequestForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            
            # Handle assignment: prefer profile if exists (legacy), else user
            if hasattr(request.user, 'employee_profile'):
                ticket.employee = request.user.employee_profile
            else:
                ticket.employee = request.user
                
            ticket.save()
            messages.success(request, "Ticket request submitted.")
            return redirect('ticket_list')
    else:
        form = TicketRequestForm()
    return render(request, 'leaves/ticket_form.html', {'form': form})
@login_required
def leave_detail(request, pk):
    from django.shortcuts import get_object_or_404
    from django.core.exceptions import PermissionDenied
    leave = get_object_or_404(LeaveRequest, pk=pk)
    
    # Permission Check
    user = request.user
    can_view = False
    
    if user.is_superuser or user.is_admin() or user.is_ceo():
        can_view = True
    elif leave.employee == user:
        can_view = True
    elif leave.assigned_manager == user and (user.role in ['PROJECT_MANAGER', 'CEO'] or user.additional_role in ['PROJECT_MANAGER', 'CEO']):
        can_view = True
    elif user.role == 'HR_MANAGER' and leave.status in ['MGR_APPROVED', 'HR_PROCESSED', 'APPROVED', 'REJECTED']:
        can_view = True
        
    if not can_view:
        raise PermissionDenied("You do not have permission to view this leave request.")
        
    return render(request, 'leaves/leave_detail.html', {'leave': leave})

@login_required
def leave_approve(request, pk):
    from django.shortcuts import get_object_or_404
    leave = get_object_or_404(LeaveRequest, pk=pk)
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('manager_comment', '')
        
        if action == 'approve':
            # Strict Single-Stage Workflow:
            # PENDING -> APPROVED (Only by Assigned Manager)
            
            is_assigned_manager = (leave.assigned_manager == user)
            
            if leave.status == LeaveRequest.Status.PENDING:
                if is_assigned_manager:
                    # Final Audit/Deduction
                    from .models import LeaveBalance
                    balance, created = LeaveBalance.objects.get_or_create(
                        employee=leave.employee,
                        leave_type=leave.leave_type,
                        year=leave.start_date.year,
                        defaults={'total_entitlement': leave.leave_type.days_entitlement, 'days_used': 0}
                    )
                    balance.days_used = float(balance.days_used) + float(leave.duration_days)
                    balance.save()

                    leave.status = LeaveRequest.Status.APPROVED
                    leave.approved_by = request.user
                    leave.manager_comment = comment
                    leave.save()
                    messages.success(request, "Leave request approved.")
                else:
                    messages.error(request, "Only the assigned manager can approve this request.")
                    return redirect('leave_detail', pk=pk)
            
            elif leave.status == LeaveRequest.Status.APPROVED:
                 messages.info(request, "This request is already approved.")
                 return redirect('leave_detail', pk=pk)
            
            else:
                 messages.error(request, "Cannot approve request in current status.")
                 return redirect('leave_detail', pk=pk)
                
        elif action == 'reject':
             # Strict Rejection Logic (Assigned Manager Only)
             is_assigned_manager = (leave.assigned_manager == user)
             
             if not is_assigned_manager:
                 messages.error(request, "Only the assigned manager can reject this request.")
                 return redirect('leave_detail', pk=pk)

             # Reversal Logic (If transitioning from APPROVED to REJECTED - unlikely in strict flow but safe to keep)
             if leave.status == LeaveRequest.Status.APPROVED:
                from .models import LeaveBalance
                try:
                    balance = LeaveBalance.objects.get(
                        employee=leave.employee,
                        leave_type=leave.leave_type,
                        year=leave.start_date.year
                    )
                    balance.days_used = max(0.0, float(balance.days_used) - float(leave.duration_days))
                    balance.save()
                except LeaveBalance.DoesNotExist:
                    pass

             leave.status = LeaveRequest.Status.REJECTED
             leave.approved_by = request.user
             leave.manager_comment = comment
             leave.save()
             messages.warning(request, "Leave rejected.")

        elif action == 'cancel':
            # Employee cancelling own request
            if leave.employee == request.user or request.user.is_superuser:
                # Reversal Logic (If transitioning from APPROVED to CANCELLED)
                if leave.status == LeaveRequest.Status.APPROVED:
                    from .models import LeaveBalance
                    try:
                        balance = LeaveBalance.objects.get(
                            employee=leave.employee,
                            leave_type=leave.leave_type,
                            year=leave.start_date.year
                        )
                        balance.days_used = max(0.0, float(balance.days_used) - float(leave.duration_days))
                        balance.save()
                    except LeaveBalance.DoesNotExist:
                        pass

                leave.status = LeaveRequest.Status.CANCELLED
                leave.save()
                messages.info(request, "Leave request cancelled.")

    # Redirect logic: prefer 'next' param, then referrer for better UX
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url:
        return redirect(next_url)
        
    return redirect('leave_detail', pk=pk)
from .forms import LeaveRequestForm, LeaveTypeForm

@login_required
def leave_settings(request):
    user = request.user
    if not user.is_staff and not user.is_admin() and not user.is_ceo():
        return redirect('dashboard')
    # Filter for active or archived
    status_filter = request.GET.get('status', 'active')
    if status_filter == 'archived':
        leave_types = LeaveType.objects.filter(is_active=False)
    else:
        leave_types = LeaveType.objects.filter(is_active=True)
        
    return render(request, 'leaves/leave_settings.html', {
        'leave_types': leave_types,
        'current_status': status_filter
    })

@login_required
def leave_type_add(request):
    user = request.user
    if not user.is_staff and not user.is_admin() and not user.is_ceo():
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = LeaveTypeForm(request.POST)
        if form.is_valid():
            ltype = form.save(commit=False)
            # Auto-generate code from name (e.g. Annual Leave -> ANN, Sick Leave -> SICK)
            import uuid
            # Simple code gen: first 3 letters upper case. Ensure unique.
            base_code = ltype.name[:3].upper()
            ltype.code = base_code
            
            # Very basic collision handling (in real app, do loop check)
            if LeaveType.objects.filter(code=base_code).exists():
                 ltype.code = base_code + str(uuid.uuid4())[:2].upper()
            
            ltype.save()
            
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                obj=ltype,
                request=request,
                module=AuditLog.Module.LEAVES,
                object_repr=ltype.name
            )
            
            messages.success(request, "Leave Type added.")
            return redirect('leave_settings')
    else:
        form = LeaveTypeForm()
    return render(request, 'leaves/leave_type_form.html', {'form': form})

@login_required
def leave_type_edit(request, pk):
    user = request.user
    if not user.is_staff and not user.is_admin() and not user.is_ceo():
        return redirect('dashboard')
        
    ltype = get_object_or_404(LeaveType, pk=pk)
    
    # Capture old state for audit
    old_state = {
        'name': ltype.name,
        'days_entitlement': ltype.days_entitlement,
        'is_paid': ltype.is_paid,
        'accrual_frequency': ltype.accrual_frequency
    }
    
    if request.method == 'POST':
        form = LeaveTypeForm(request.POST, instance=ltype)
        if form.is_valid():
            ltype = form.save()
            
            # Calculate changes
            changes = {}
            for field, old_val in old_state.items():
                new_val = getattr(ltype, field)
                if old_val != new_val:
                    changes[field] = [str(old_val), str(new_val)]
            
            if changes:
                AuditLog.log(
                    user=request.user,
                    action=AuditLog.Action.UPDATE,
                    obj=ltype,
                    changes=changes,
                    request=request,
                    module=AuditLog.Module.LEAVES,
                    object_repr=ltype.name
                )
            
            messages.success(request, "Leave Type updated.")
            return redirect('leave_settings')
    else:
        form = LeaveTypeForm(instance=ltype)
    return render(request, 'leaves/leave_type_form.html', {'form': form})

@login_required
def leave_type_delete(request, pk):
    user = request.user
    if not user.is_staff and not user.is_admin() and not user.is_ceo():
        return redirect('dashboard')
        
    ltype = get_object_or_404(LeaveType, pk=pk)
    if request.method == 'POST':
        ltype.is_active = False
        ltype.status = LeaveType.Status.INACTIVE
        ltype.save()
        messages.success(request, f"Leave policy '{ltype.name}' has been archived.")
        return redirect('leave_settings')
    return redirect('leave_settings')

@login_required
def leave_type_restore(request, pk):
    user = request.user
    if not user.is_staff and not user.is_admin() and not user.is_ceo():
        return redirect('dashboard')
        
    ltype = get_object_or_404(LeaveType, pk=pk)
    if request.method == 'POST':
        ltype.is_active = True
        ltype.status = LeaveType.Status.ACTIVE
        ltype.save()
        messages.success(request, f"Leave policy '{ltype.name}' has been restored.")
        return redirect('leave_settings')
    return redirect('leave_settings')
from django.http import JsonResponse
from .models import LeaveRequest
from django.contrib.auth.decorators import login_required

@login_required
def check_updates(request):
    """
    API endpoint for checking updates to leave requests.
    Returns the latest status of requests involving the current user.
    """
    user = request.user
    
    # Return status of the user's recent requests (last 20 for coverage)
    recent_requests = LeaveRequest.objects.filter(employee=user).order_by('-updated_at')[:20]
    data = [{'id': r.id, 'status': r.status} for r in recent_requests]
    
    return JsonResponse({'requests': data})

@login_required
def lop_adjustment_request(request, payroll_id=None):
    """
    Initiate a request to convert LOP to Annual Leave.
    """
    user = request.user
    payroll_entry = None
    max_lop = 0.0
    
    # 1. Determine Employee and Max LOP
    if payroll_id:
        payroll_entry = get_object_or_404(PayrollEntry, pk=payroll_id)
        # Auth check
        is_manager = payroll_entry.employee.managers.filter(pk=user.id).exists()
        if payroll_entry.employee != user and not (user.is_admin() or user.is_hr() or user.is_ceo() or is_manager):
             messages.error(request, "Permission denied.")
             return redirect('payroll_list')
        
        emp = payroll_entry.employee
        # Convert total hours to days, floored to the nearest 0.5 day (e.g., 7.3 -> 7.0, 7.8 -> 7.5)
        import math
        max_lop = math.floor((float(payroll_entry.shortfall_work_hours) / 8.0) * 2) / 2.0
        
        # Check if already pending
        if LOPAdjustment.objects.filter(payroll_entry=payroll_entry, status='PENDING').exists():
            messages.warning(request, "There is already a pending adjustment for this payroll entry.")
            return redirect('payroll_detail', pk=payroll_entry.batch.pk)
    else:
        emp = user
        # Find most recent entry with actual shortfall
        payroll_entry = PayrollEntry.objects.filter(employee=emp, shortfall_work_hours__gt=0).order_by('-created_at').first()
        if payroll_entry:
             # Check if already pending
            if LOPAdjustment.objects.filter(payroll_entry=payroll_entry, status='PENDING').exists():
                messages.warning(request, "Pending conversion request already exists.")
                return redirect('leave_list')
            import math
            max_lop = math.floor((float(payroll_entry.shortfall_work_hours) / 8.0) * 2) / 2.0
        else:
            messages.info(request, "No convertible Loss of Pay found in your payroll history.")
            return redirect('leave_list')

    if max_lop <= 0:
        messages.warning(request, "No LOP hours available to convert.")
        return redirect('leave_list')

    # 2. Get Annual Leave Balance
    try:
        ann_type = LeaveType.objects.get(code='ANN')
        from django.utils import timezone
        import math
        balance, _ = LeaveBalance.objects.get_or_create(
            employee=emp,
            leave_type=ann_type,
            year=timezone.now().year
        )
        # Floor to nearest 0.5 to avoid floating point remnants (e.g. 0.09 -> 0.0)
        raw_al = float(balance.remaining)
        max_al = math.floor(raw_al * 2) / 2.0
    except LeaveType.DoesNotExist:
        messages.error(request, "Annual Leave policy (ANN) not found.")
        return redirect('leave_list')

    if max_al <= 0:
        messages.warning(request, "You have no Annual Leave balance available to convert LOP.")
        return redirect('leave_list')

    # Cap max_lop by available AL — can't convert more than you have AL for
    max_lop = min(max_lop, max_al)

    if request.method == 'POST':
        form = LOPAdjustmentForm(request.POST, max_lop=max_lop, max_al=max_al)
        if form.is_valid():
            adj = form.save(commit=False)
            adj.employee = emp
            adj.payroll_entry = payroll_entry
            adj.requested_by = user
            adj.original_lop_days = max_lop
            adj.remaining_lop_days = float(max_lop) - float(adj.requested_annual_leave_days)
            adj.converted_hours = float(adj.requested_annual_leave_days) * 8.0
            
            # Auto-approve for all users
            from django.db import transaction
            from decimal import Decimal
            from django.utils import timezone
            from django.db.models import Sum
            from payroll.models import PayrollDeduction, DeductionComponent
            
            try:
                with transaction.atomic():
                    # 1. Update Leave Balance
                    ann_type = LeaveType.objects.get(code='ANN')
                    balance, _ = LeaveBalance.objects.get_or_create(
                        employee=adj.employee, 
                        leave_type=ann_type, 
                        year=timezone.now().year
                    )
                    
                    if float(balance.remaining) < float(adj.requested_annual_leave_days):
                         raise ValueError("Insufficient Annual Leave balance remaining.")
                    
                    balance.days_used = float(balance.days_used) + float(adj.requested_annual_leave_days)
                    balance.save()
                    
                    # 2. Update Payroll Entry
                    if adj.payroll_entry:
                         pe = adj.payroll_entry
                         pe.shortfall_work_hours = max(Decimal('0'), pe.shortfall_work_hours - Decimal(str(adj.converted_hours)))
                         pe.days_absent = max(0, pe.days_absent - int(adj.requested_annual_leave_days))
                         pe.lop_deduction = round(pe.shortfall_work_hours * pe.employee.hourly_salary, 2)
                         
                         lop_component = DeductionComponent.objects.filter(name="Loss of Pay (Shortfall)").first()
                         if lop_component:
                             lop_ded = PayrollDeduction.objects.filter(payroll_entry=pe, component=lop_component).first()
                             if lop_ded:
                                 if pe.lop_deduction > 0:
                                     lop_ded.amount = pe.lop_deduction
                                     lop_ded.approved_amount = pe.lop_deduction
                                     lop_ded.save()
                                 else:
                                     lop_ded.delete()
                         
                         total_ded = pe.breakdown_deductions.filter(is_waived=False).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                         pe.deductions = round(total_ded, 2)
                         pe.net_salary = max(Decimal('0.00'), pe.gross_salary - pe.deductions)
                         pe.save()

                    adj.status = LOPAdjustment.Status.APPROVED
                    adj.authorized_by = user
                    adj.authorized_at = timezone.now()
                    adj.save()
                    messages.success(request, f"Successfully converted {adj.requested_annual_leave_days} days of LOP for {emp.full_name}.")
            except Exception as e:
                messages.error(request, f"Direct conversion failed: {str(e)}")
                return render(request, 'leaves/lop_adjustment_form.html', {
                    'form': form, 'payroll_entry': payroll_entry, 'employee': emp, 'max_lop': max_lop, 'max_al': max_al, 'hourly_rate': float(emp.hourly_salary or 0)
                })
            
            if payroll_entry and payroll_entry.batch:
                return redirect('payroll_detail', pk=payroll_entry.batch.pk)
            return redirect('leave_list')
    else:
        form = LOPAdjustmentForm(max_lop=max_lop, max_al=max_al)
        
    return render(request, 'leaves/lop_adjustment_form.html', {
        'form': form,
        'payroll_entry': payroll_entry,
        'employee': emp,
        'max_lop': max_lop,
        'max_al': max_al,
        'hourly_rate': float(emp.hourly_salary or 0)
    })

@login_required
def lop_adjustment_list(request):
    """
    Birds-eye view for Admin/CEO/HR of all LOP conversions.
    """
    user = request.user
    if not (user.is_admin() or user.is_hr() or user.is_ceo()):
        # Regular employees see their own
        adjustments = LOPAdjustment.objects.filter(employee=user).order_by('-created_at')
    else:
        adjustments = LOPAdjustment.objects.all().order_by('-created_at')

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, adjustments, default_limit=10, unique_id='_adjs')
    
    return render(request, 'leaves/lop_adjustment_list.html', {
        'adjustments': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True
    })

@login_required
def lop_adjustment_detail(request, pk):
    adj = get_object_or_404(LOPAdjustment, pk=pk)
    user = request.user
    
    # Permission check
    is_manager = adj.employee.managers.filter(pk=user.id).exists()
    if not (user.is_admin() or user.is_hr() or user.is_ceo() or adj.employee == user or is_manager):
         messages.error(request, "Permission denied.")
         return redirect('leave_list')
         
    return render(request, 'leaves/lop_adjustment_detail.html', {'adj': adj})

@login_required
def lop_adjustment_approve(request, pk):
    adj = get_object_or_404(LOPAdjustment, pk=pk)
    user = request.user
    
    if not (user.is_admin() or user.is_hr() or user.is_ceo()):
        messages.error(request, "Only Admin, CEO, or HR can approve this adjustment.")
        return redirect('lop_adjustment_detail', pk=pk)

    if adj.status != LOPAdjustment.Status.PENDING:
         messages.info(request, "This adjustment has already been processed.")
         return redirect('lop_adjustment_detail', pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            from django.db import transaction
            from decimal import Decimal
            try:
                with transaction.atomic():
                    # 1. Update Leave Balance
                    ann_type = LeaveType.objects.get(code='ANN')
                    balance, _ = LeaveBalance.objects.get_or_create(
                        employee=adj.employee, 
                        leave_type=ann_type, 
                        year=adj.created_at.year
                    )
                    
                    if float(balance.remaining) < float(adj.requested_annual_leave_days):
                         raise ValueError("Insufficient Annual Leave balance remaining.")
                    
                    balance.days_used = float(balance.days_used) + float(adj.requested_annual_leave_days)
                    balance.save()
                    
                    # 2. Update Payroll Entry if linked
                    if adj.payroll_entry:
                         pe = adj.payroll_entry
                         # Reduce shortfall
                         pe.shortfall_work_hours = max(Decimal('0'), pe.shortfall_work_hours - Decimal(str(adj.converted_hours)))
                         
                         # Also reduce days_absent count if full days adjusted
                         adjusted_full_days = int(adj.requested_annual_leave_days)
                         pe.days_absent = max(0, pe.days_absent - adjusted_full_days)
                         
                         # Recalculate LOP deduction amount
                         hourly_rate = pe.employee.hourly_salary
                         pe.lop_deduction = round(pe.shortfall_work_hours * hourly_rate, 2)
                         
                         # Update the PayrollDeduction record for LOP
                         from payroll.models import PayrollDeduction, DeductionComponent
                         lop_component = DeductionComponent.objects.filter(name="Loss of Pay (Shortfall)").first()
                         if lop_component:
                             lop_ded = PayrollDeduction.objects.filter(
                                 payroll_entry=pe, component=lop_component
                             ).first()
                             if lop_ded:
                                 if pe.lop_deduction > 0:
                                     lop_ded.amount = pe.lop_deduction
                                     lop_ded.approved_amount = pe.lop_deduction
                                     lop_ded.save()
                                 else:
                                     lop_ded.delete()
                         
                         # Recalculate total deductions from all PayrollDeduction records
                         from django.db.models import Sum
                         total_ded = pe.breakdown_deductions.filter(is_waived=False).aggregate(
                             total=Sum('amount')
                         )['total'] or Decimal('0.00')
                         pe.deductions = round(total_ded, 2)
                         
                         # Update net salary
                         pe.net_salary = max(Decimal('0.00'), pe.gross_salary - pe.deductions)
                         pe.save()

                    adj.status = LOPAdjustment.Status.APPROVED
                    adj.authorized_by = user
                    from django.utils import timezone
                    adj.authorized_at = timezone.now()
                    adj.save()
                    
                    messages.success(request, f"Approved: {adj.requested_annual_leave_days} days converted.")
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('lop_adjustment_detail', pk=pk)
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
                return redirect('lop_adjustment_detail', pk=pk)
            
        elif action == 'reject':
            adj.status = LOPAdjustment.Status.REJECTED
            adj.rejection_reason = request.POST.get('rejection_reason', '')
            adj.authorized_by = user
            adj.save()
            messages.warning(request, "Adjustment request rejected.")
            
    return redirect('lop_adjustment_detail', pk=pk)

@login_required
def lop_adjustment_report(request):
    """
    Adjustment Log for Monthly Reconciliation and Trend Tracking.
    """
    user = request.user
    if not (user.is_admin() or user.is_hr() or user.is_ceo()):
        return redirect('dashboard')
        
    adjustments = LOPAdjustment.objects.filter(status='APPROVED').order_by('-authorized_at')
    
    # Simple Monthly Grouping / Stats
    from django.db.models import Sum, Count
    stats = adjustments.aggregate(
        total_days=Sum('requested_annual_leave_days'),
        total_count=Count('id')
    )
    
    # Trend: Top employees using this conversion
    trends = LOPAdjustment.objects.filter(status='APPROVED').values(
        'employee__full_name', 'employee__employee_id'
    ).annotate(
        req_count=Count('id'),
        total_days=Sum('requested_annual_leave_days')
    ).order_by('-total_days')[:10]
    
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, adjustments, default_limit=10, unique_id='_adjs')
    
    return render(request, 'leaves/lop_adjustment_log.html', {
        'adjustments': page_obj,
        'stats': stats,
        'trends': trends,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True
    })

@login_required
def lop_adjustment_bulk(request):
    """
    Batch process interface for HR.
    """
    user = request.user
    if not (user.is_admin() or user.is_hr() or user.is_ceo()):
        return redirect('dashboard')
        
    pending = LOPAdjustment.objects.filter(status='PENDING')
    
    if request.method == 'POST':
        selected_ids = request.POST.getlist('adj_ids')
        action = request.POST.get('batch_action')
        
        if not selected_ids:
            messages.warning(request, "No requests selected.")
        else:
            from django.db import transaction
            from decimal import Decimal
            from django.utils import timezone
            
            count = 0
            errors = []
            
            for adj_id in selected_ids:
                try:
                    with transaction.atomic():
                        adj = LOPAdjustment.objects.select_for_update().get(pk=adj_id, status=LOPAdjustment.Status.PENDING)
                        
                        if action == 'approve':
                            # 1. Update Leave Balance
                            ann_type = LeaveType.objects.get(code='ANN')
                            balance, _ = LeaveBalance.objects.get_or_create(
                                employee=adj.employee, 
                                leave_type=ann_type, 
                                year=adj.created_at.year
                            )
                            
                            if float(balance.remaining) < float(adj.requested_annual_leave_days):
                                 errors.append(f"Insufficient balance for {adj.employee.full_name}")
                                 continue
                            
                            balance.days_used = float(balance.days_used) + float(adj.requested_annual_leave_days)
                            balance.save()
                            
                            # 2. Update Payroll Entry if linked
                            if adj.payroll_entry:
                                 pe = adj.payroll_entry
                                 pe.shortfall_work_hours = max(Decimal('0'), pe.shortfall_work_hours - Decimal(str(adj.converted_hours)))
                                 
                                 # Reduce days_absent proportionally
                                 adjusted_full_days = int(adj.requested_annual_leave_days)
                                 pe.days_absent = max(0, pe.days_absent - adjusted_full_days)
                                 
                                 pe.lop_deduction = round(pe.shortfall_work_hours * pe.employee.hourly_salary, 2)
                                 
                                 # Update the PayrollDeduction record for LOP
                                 from payroll.models import PayrollDeduction, DeductionComponent
                                 lop_component = DeductionComponent.objects.filter(name="Loss of Pay (Shortfall)").first()
                                 if lop_component:
                                     lop_ded = PayrollDeduction.objects.filter(
                                         payroll_entry=pe, component=lop_component
                                     ).first()
                                     if lop_ded:
                                         if pe.lop_deduction > 0:
                                             lop_ded.amount = pe.lop_deduction
                                             lop_ded.approved_amount = pe.lop_deduction
                                             lop_ded.save()
                                         else:
                                             lop_ded.delete()
                                 
                                 # Recalculate total deductions from all PayrollDeduction records
                                 from django.db.models import Sum
                                 total_ded = pe.breakdown_deductions.filter(is_waived=False).aggregate(
                                     total=Sum('amount')
                                 )['total'] or Decimal('0.00')
                                 pe.deductions = round(total_ded, 2)
                                 
                                 pe.net_salary = max(Decimal('0.00'), pe.gross_salary - pe.deductions)
                                 pe.save()

                            adj.status = LOPAdjustment.Status.APPROVED
                            adj.authorized_by = user
                            adj.authorized_at = timezone.now()
                            adj.save()
                            count += 1
                            
                        elif action == 'reject':
                            adj.status = LOPAdjustment.Status.REJECTED
                            adj.authorized_by = user
                            adj.save()
                            count += 1
                except Exception as e:
                    errors.append(f"Error processing request for {adj.employee.full_name}: {str(e)}")
            
            if count:
                messages.success(request, f"Successfully processed {count} adjustments.")
            if errors:
                for err in errors:
                    messages.error(request, err)
            
            return redirect('lop_adjustment_bulk')
            
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, pending, default_limit=10, unique_id='_pending')
            
    return render(request, 'leaves/lop_adjustment_bulk.html', {
        'pending': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True
    })

@login_required
def lop_adjustment_delete(request, pk):
    """
    Remove an LOP adjustment and reverse any changes made to attendance/balance.
    """
    adj = get_object_or_404(LOPAdjustment, pk=pk)
    user = request.user
    
    # Permissions
    if not (user.is_admin() or user.is_hr() or user.is_ceo()):
         # Employees can remove their own PENDING requests
         if not (adj.employee == user and adj.status == LOPAdjustment.Status.PENDING):
              messages.error(request, "Permission denied.")
              return redirect('lop_adjustment_list')

    if request.method == 'POST':
        from django.db import transaction
        from decimal import Decimal
        try:
            with transaction.atomic():
                if adj.status == LOPAdjustment.Status.APPROVED:
                    # 1. Revert Leave Balance
                    try:
                        ann_type = LeaveType.objects.get(code='ANN')
                        # Find balance for the year it was created (matching approval year)
                        balance = LeaveBalance.objects.filter(
                            employee=adj.employee, 
                            leave_type=ann_type, 
                            year=adj.created_at.year
                        ).first()
                        
                        if balance:
                            balance.days_used = max(0.0, float(balance.days_used) - float(adj.requested_annual_leave_days))
                            balance.save()
                    except LeaveType.DoesNotExist:
                        pass # Policy might have been deleted, but we should still revert payroll
                    
                    # 2. Restore Payroll Entry Stats
                    if adj.payroll_entry:
                        pe = adj.payroll_entry
                        # Add back shortfall hours
                        pe.shortfall_work_hours += Decimal(str(adj.converted_hours))
                        
                        # Add back days_absent
                        adjusted_full_days = int(adj.requested_annual_leave_days)
                        pe.days_absent += adjusted_full_days
                        
                        # Recalculate LOP deduction amount
                        hourly_rate = pe.employee.hourly_salary
                        pe.lop_deduction = round(pe.shortfall_work_hours * hourly_rate, 2)
                        
                        # Update the PayrollDeduction record for LOP
                        from payroll.models import PayrollDeduction, DeductionComponent
                        lop_component = DeductionComponent.objects.filter(name="Loss of Pay (Shortfall)").first()
                        if lop_component:
                            lop_ded = PayrollDeduction.objects.filter(
                                payroll_entry=pe, component=lop_component
                            ).first()
                            if lop_ded:
                                # Restore the original LOP amount
                                lop_ded.amount = pe.lop_deduction
                                lop_ded.approved_amount = pe.lop_deduction
                                lop_ded.save()
                            else:
                                # Re-create the LOP deduction record if it was deleted
                                if pe.lop_deduction > 0:
                                    PayrollDeduction.objects.create(
                                        payroll_entry=pe,
                                        component=lop_component,
                                        amount=pe.lop_deduction,
                                        approved_amount=pe.lop_deduction,
                                        is_waived=False
                                    )
                        
                        # Recalculate total deductions from all PayrollDeduction records
                        from django.db.models import Sum
                        total_ded = pe.breakdown_deductions.filter(is_waived=False).aggregate(
                            total=Sum('amount')
                        )['total'] or Decimal('0.00')
                        pe.deductions = round(total_ded, 2)
                        
                        # Update net salary
                        pe.net_salary = max(Decimal('0.00'), pe.gross_salary - pe.deductions)
                        pe.save()
                
                adj.delete()
                messages.success(request, f"Successfully removed LOP adjustment. Changes were reversed.")
        except Exception as e:
            messages.error(request, f"Failed to remove adjustment: {str(e)}")
            
    return redirect('lop_adjustment_list')
