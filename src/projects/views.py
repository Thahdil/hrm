from django.shortcuts import render, redirect, get_object_or_404
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from .models import Project, ProjectHours
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def project_list(request):
    """
    View for listing and creating projects (for CEO/Managers).
    """
    is_authorized = request.user.role in ['ADMIN', 'CEO'] or getattr(request.user, 'is_project_manager', False)
    
    if request.method == 'POST' and is_authorized:
        name = request.POST.get('name')
        description = request.POST.get('description')
        employee_ids = request.POST.getlist('employees')
        
        project = Project.objects.create(name=name, description=description)
        if employee_ids:
            project.assigned_employees.set(employee_ids)
        
        messages.success(request, f"Project '{name}' created successfully.")
        return redirect('project_list')

    active_projects = Project.objects.filter(is_active=True).prefetch_related('assigned_employees')
    completed_projects = Project.objects.filter(is_active=False).prefetch_related('assigned_employees')
    all_employees = User.objects.filter(is_active=True).exclude(role__in=['ADMIN', 'CEO', 'PROJECT_MANAGER']).order_by('full_name')
    
    from core.utils.pagination import get_paginated_data
    paginator_active, page_obj_active = get_paginated_data(request, active_projects, default_limit=10)
    # We might want separate pagination for completed, but for now let's just paginate active
    # or both with the same control. 
    # Actually, let's just pass the same pagination context for active.
    
    context = {
        'active_projects': page_obj_active,
        'completed_projects': completed_projects, # Keep all completed for now or paginate separately? 
        'all_employees': all_employees,
        'is_authorized': is_authorized,
        'paginator': paginator_active,
        'page_obj': page_obj_active,
        'is_paginated': True
    }
    return render(request, 'projects/project_list.html', context)

@login_required
def add_project_hours(request):
    """
    View for adding project hours with 8-hour cap logic.
    Employees see only projects they are assigned to.
    """
    # Filter projects assigned to the current user
    assigned_projects = request.user.assigned_projects.filter(is_active=True)
    
    today = timezone.now().date()
    
    # Calculate already logged standard hours for today
    logged_standard = ProjectHours.objects.filter(
        employee=request.user, 
        date=today
    ).aggregate(Sum('standard_hours'))['standard_hours__sum'] or Decimal('0.0')

    if request.method == 'POST':
        project_id = request.POST.get('project')
        standard = Decimal(request.POST.get('standard_hours', '0') or '0')
        extra = Decimal(request.POST.get('extra_time', '0') or '0')
        overtime = Decimal(request.POST.get('overtime', '0') or '0')
        task = request.POST.get('task_description')
        
        project = get_object_or_404(Project, id=project_id)
        
        # Validation: Standard cap 8h
        if (logged_standard + standard) > Decimal('8.0'):
            messages.error(request, "Total standard hours for today cannot exceed 8.0 hours.")
        else:
            ProjectHours.objects.create(
                employee=request.user,
                project=project,
                date=today,
                standard_hours=standard,
                extra_time=extra,
                overtime=overtime,
                task_description=task
            )
            messages.success(request, "Hours logged successfully.")
            return redirect('add_project_hours')

    # Detailed logs for today
    today_logs = ProjectHours.objects.filter(
        employee=request.user, 
        date=today
    ).select_related('project')

    context = {
        'title': 'Add Project Hours',
        'projects': assigned_projects,
        'today': today,
        'logged_standard': logged_standard,
        'remaining_standard': Decimal('8.0') - logged_standard,
        'today_logs': today_logs,
    }
    return render(request, 'projects/add_hours.html', context)

@login_required
def project_detail(request, pk):
    """
    Detailed report of a project: total hours and task descriptions.
    Restricted to CEO/Admin/Project Managers.
    """
    project = get_object_or_404(Project, pk=pk)
    is_authorized = request.user.role in ['ADMIN', 'CEO'] or getattr(request.user, 'is_project_manager', False)
    
    if not is_authorized:
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
    
    # Get selected period from request — 'all' means complete portfolio
    now = timezone.now()
    import datetime

    show_all = request.GET.get('period') == 'all'
    selected_month = int(request.GET.get('month', now.month))
    selected_year = int(request.GET.get('year', now.year))

    if show_all:
        base_qs = ProjectHours.objects.filter(project=project)
        label = "Complete Portfolio"
    else:
        selected_date = datetime.date(selected_year, selected_month, 1)
        label = selected_date.strftime('%B %Y')
        base_qs = ProjectHours.objects.filter(
            project=project,
            date__year=selected_year,
            date__month=selected_month
        )

    # Aggregate summaries
    stats = base_qs.aggregate(
        total_std=Sum('standard_hours'),
        total_extra=Sum('extra_time'),
        total_ot=Sum('overtime')
    )

    # Aggregated hours per employee
    employee_stats = base_qs.values(
        'employee__full_name',
        'employee__username',
        'employee__id'
    ).annotate(
        total_std=Sum('standard_hours'),
        total_extra=Sum('extra_time'),
        total_ot=Sum('overtime'),
        total_combined=Sum('standard_hours') + Sum('extra_time') + Sum('overtime')
    ).order_by('-total_combined')

    # Detailed logs
    logs = base_qs.select_related('employee').order_by('-date')

    # Generate months from project creation month up to current month
    available_months = []
    start = project.created_at.date().replace(day=1)
    current = now.date().replace(day=1)
    cursor = current
    while cursor >= start:
        available_months.append({
            'month': cursor.month,
            'year': cursor.year,
            'name': cursor.strftime('%B %Y')
        })
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)

    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, logs, default_limit=10)

    context = {
        'project': project,
        'stats': stats,
        'employee_stats': employee_stats,
        'logs': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'show_all': show_all,
        'current_month_name': label,
        'available_months': available_months,
    }
    return render(request, 'projects/project_detail.html', context)


@login_required
def toggle_project_status(request, pk):
    """
    Toggle a project's active/completed status. Restricted to CEO/Admin/Project Managers.
    """
    project = get_object_or_404(Project, pk=pk)
    is_authorized = request.user.role in ['ADMIN', 'CEO'] or getattr(request.user, 'is_project_manager', False)

    if not is_authorized:
        messages.error(request, "Permission denied.")
        return redirect('project_list')

    if request.method == 'POST':
        project.is_active = not project.is_active
        project.save()
        status = "activated" if project.is_active else "marked as completed"
        messages.success(request, f"Project '{project.name}' has been {status}.")

    return redirect('project_detail', pk=project.pk)


@login_required
def edit_project_team(request, pk):
    """
    Update the assigned team for a project. Restricted to CEO/Admin/Project Managers.
    """
    is_authorized = request.user.role in ['ADMIN', 'CEO'] or getattr(request.user, 'is_project_manager', False)
    if not is_authorized:
        messages.error(request, "Permission denied.")
        return redirect('project_list')

    project = get_object_or_404(Project, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        employee_ids = request.POST.getlist('employees')
        
        if name:
            project.name = name
        if description is not None:
            project.description = description
            
        project.save()
        project.assigned_employees.set(employee_ids)
        messages.success(request, f"Project '{project.name}' updated successfully.")
        
    # Redirect back to the referring page if available, else project list
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('project_list')

