from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import LeaveRequest, LeaveType
from .models import LeaveRequest, LeaveType
from .forms import LeaveRequestForm, LeaveTypeForm
from django.contrib import messages
from core.models import AuditLog
from django.db.models import Q

@login_required
def leave_list(request):
    user = request.user
    is_admin = user.is_staff or user.is_admin() or user.is_hr() or user.is_ceo() or user.is_project_manager()
    
    import datetime
    current_year = datetime.date.today().year
    
    balances = []
    if not is_admin:
        from .models import LeaveBalance
        from django.utils import timezone
        today = timezone.now().date()
        
        valid_types = LeaveType.objects.filter(is_active=True)
        # Filter by gender if available
        if user.gender:
            valid_types = valid_types.filter(Q(eligibility_gender='ALL') | Q(eligibility_gender=user.gender))

        for lt in valid_types:
            is_fixed_monthly = (lt.accrual_frequency == 'MONTHLY' and (lt.duration_days == 1 or 'Sick' in lt.name or 'Normal' in lt.name))
            
            if is_fixed_monthly:
                total_quota = 1.0
                used = LeaveRequest.objects.filter(
                    employee=user,
                    leave_type=lt,
                    status=LeaveRequest.Status.APPROVED,
                    start_date__month=today.month,
                    start_date__year=today.year
                ).count()
                
                balances.append({
                    'leave_type': lt,
                    'total_entitlement': total_quota,
                    'remaining': max(0, total_quota - float(used))
                })
            else:
                total_quota = lt.days_entitlement
                if lt.accrual_frequency == 'MONTHLY':
                    total_quota = (lt.days_entitlement / 12) * today.month

                balance_obj, created = LeaveBalance.objects.get_or_create(
                    employee=user,
                    leave_type=lt,
                    year=current_year,
                    defaults={'total_entitlement': total_quota, 'days_used': 0}
                )
                
                if not created and balance_obj.total_entitlement != total_quota:
                    balance_obj.total_entitlement = total_quota
                    balance_obj.save()
                    
                balances.append(balance_obj)


    # Permission Logic
    if user.is_superuser or user.is_admin() or user.is_ceo():
        # Admin / CEO sees ALL (except cancelled)
        leaves = LeaveRequest.objects.exclude(status='CANCELLED').order_by('-created_at')
        
    elif user.is_hr():
        # HR sees MGR_APPROVED (waiting for HR) + History + Own Requests (except cancelled)
        leaves = LeaveRequest.objects.filter(
            Q(status__in=['MGR_APPROVED', 'HR_PROCESSED', 'APPROVED', 'REJECTED']) | 
            Q(employee=user)
        ).exclude(status='CANCELLED').order_by('-created_at')
        
    else:
        # Check PM logic
        is_pm = False
        if user.is_project_manager():
                is_pm = True
                
        if is_pm:
             # PM sees Assigned Requests + Own Requests (except cancelled)
            leaves = LeaveRequest.objects.filter(
                Q(assigned_manager=user) | Q(employee=user)
            ).exclude(status='CANCELLED').order_by('-created_at')
        else:
             # Regular Employee (shows all their requests including cancelled)
            leaves = LeaveRequest.objects.filter(employee=user).order_by('-created_at')
             
    return render(request, 'leaves/leave_list.html', {'leaves': leaves, 'is_admin': is_admin, 'balances': balances})

@login_required
def leave_create(request):
    # Eligibility Logic
    from django.utils import timezone
    from django.db.models import Q
    from .models import LeaveBalance
    from datetime import date
    
    today = timezone.now().date()
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
        # Check if it's a non-accumulative monthly type
        is_fixed_monthly = (lt.accrual_frequency == 'MONTHLY' and (lt.duration_days == 1 or 'Sick' in lt.name or 'Normal' in lt.name))
        
        if is_fixed_monthly:
            total_quota = 1.0
            # Check usage THIS MONTH from requests
            used_this_month = LeaveRequest.objects.filter(
                employee=request.user,
                leave_type=lt,
                status__in=['PENDING', 'APPROVED', 'MGR_APPROVED', 'HR_PROCESSED'], # Include pending to prevent double booking
                start_date__month=today.month,
                start_date__year=today.year
            ).count()
            used = float(used_this_month)
        else:
            # Standard accrual or annual logic
            total_quota = lt.days_entitlement
            if lt.accrual_frequency == 'MONTHLY':
                total_quota = (lt.days_entitlement / 12) * today.month

            # Sync Used Days from Approved/Processed requests for the year to ensure accuracy
            approved_requests = LeaveRequest.objects.filter(
                employee=request.user,
                leave_type=lt,
                status__in=['APPROVED', 'HR_PROCESSED'],
                start_date__year=current_year
            )
            actual_used = sum(float(r.duration_days) for r in approved_requests) or 0.0

            balance, created = LeaveBalance.objects.get_or_create(
                employee=request.user,
                leave_type=lt,
                year=current_year,
                defaults={'total_entitlement': total_quota, 'days_used': actual_used}
            )
            
            if not created:
                if balance.total_entitlement != total_quota or float(balance.days_used) != float(actual_used):
                    balance.total_entitlement = total_quota
                    balance.days_used = actual_used
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
            
            # Validate balance
            requested_days = leave.duration_days
            leave_type_id = leave.leave_type.id
            
            if leave_type_id in leave_balances:
                remaining = leave_balances[leave_type_id]['remaining']
                if requested_days > remaining:
                    messages.error(
                        request, 
                        f"Insufficient leave balance. You requested {requested_days} days but only have {remaining} days remaining for {leave.leave_type.name}."
                    )
                    return render(request, 'leaves/leave_form.html', {
                        'form': form,
                        'type_config': json.dumps({lt.id: (lt.duration_days or 0) for lt in valid_types}),
                        'leave_balances': leave_balances
                    })
            
            leave.save()
            
            # Log activity
            from core.models import AuditLog
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                obj=leave,
                request=request
            )
            
            messages.success(request, f"Leave request submitted for {requested_days} days.")
            return redirect('leave_list')
    else:
        form = LeaveRequestForm(user=request.user)
        form.fields['leave_type'].queryset = valid_types
    
    if not valid_types.exists():
        messages.warning(request, "You are not eligible for any leave types at this time (Service/Gender criteria).")

    # Prepare configuration for frontend (Duration handling)
    import json
    type_config = {lt.id: (lt.duration_days or 0) for lt in valid_types}

    return render(request, 'leaves/leave_form.html', {
        'form': form, 
        'type_config': json.dumps(type_config),
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
            
    return render(request, 'leaves/ticket_list.html', {'tickets': tickets})

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
            
            from core.models import AuditLog
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                obj=ticket,
                request=request,
                module=AuditLog.Module.TICKETS,
                object_repr=f"Ticket to {ticket.destination}"
            )
            
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
            # Approval Logic
            
            # 1. Admin / CEO / HR (Final Approval Authority)
            if user.is_admin() or user.is_ceo() or user.is_hr() or user.is_superuser:
                if leave.status == LeaveRequest.Status.APPROVED:
                    messages.info(request, "This request is already approved.")
                    return redirect('leave_detail', pk=pk)
                
                # Deduction Logic
                is_fixed_monthly = (
                    leave.leave_type.accrual_frequency == 'MONTHLY' and 
                    (leave.leave_type.duration_days == 1 or 'Sick' in leave.leave_type.name or 'Normal' in leave.leave_type.name)
                )

                if not is_fixed_monthly:
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
                
                # Log activity
                from core.models import AuditLog
                AuditLog.log(
                    user=request.user,
                    action=AuditLog.Action.APPROVE,
                    obj=leave,
                    request=request
                )
                
                messages.success(request, "Leave fully approved and balance updated.")

            # 2. Project Manager (Intermediate Approval)
            elif user.is_project_manager():
                if leave.assigned_manager != request.user:
                     messages.error(request, "You are not the assigned manager for this request.")
                     return redirect('leave_detail', pk=pk)
                
                leave.status = LeaveRequest.Status.MGR_APPROVED
                leave.approved_by = request.user # Track PM approval
                leave.manager_comment = comment
                leave.save()
                messages.success(request, "Leave approved. Forwarded to HR.")
                
            else:
                 messages.error(request, "You do not have permission to approve leaves.")
                
        elif action == 'reject':
             can_reject = False
             if user.is_staff or user.is_admin() or user.is_hr():
                 can_reject = True
             elif user.is_project_manager() and leave.assigned_manager == user:
                 can_reject = True
             elif user.is_ceo():
                 can_reject = True
                 
             if can_reject:
                # Reversal Logic (If transitioning from APPROVED to REJECTED)
                if leave.status == LeaveRequest.Status.APPROVED:
                    is_fixed_monthly = (
                        leave.leave_type.accrual_frequency == 'MONTHLY' and 
                        (leave.leave_type.duration_days == 1 or 'Sick' in leave.leave_type.name or 'Normal' in leave.leave_type.name)
                    )
                    
                    if not is_fixed_monthly:
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
                
                # Log activity
                from core.models import AuditLog
                AuditLog.log(
                    user=request.user,
                    action=AuditLog.Action.REJECT,
                    obj=leave,
                    request=request
                )
                
                messages.warning(request, "Leave rejected.")
             else:
                messages.error(request, "You do not have permission to reject this request.")

        elif action == 'cancel':
            # Employee cancelling own request
            if leave.employee == request.user or request.user.is_superuser:
                # Reversal Logic (If transitioning from APPROVED to CANCELLED)
                if leave.status == LeaveRequest.Status.APPROVED:
                    is_fixed_monthly = (
                        leave.leave_type.accrual_frequency == 'MONTHLY' and 
                        (leave.leave_type.duration_days == 1 or 'Sick' in leave.leave_type.name or 'Normal' in leave.leave_type.name)
                    )
                    
                    if not is_fixed_monthly:
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
