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

    projects = Project.objects.all().prefetch_related('assigned_employees')
    all_employees = User.objects.filter(is_active=True).exclude(role__in=['ADMIN', 'CEO', 'PROJECT_MANAGER']).order_by('full_name')
    
    context = {
        'projects': projects,
        'all_employees': all_employees,
        'is_authorized': is_authorized,
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
    
    # Aggregate summaries
    stats = ProjectHours.objects.filter(project=project).aggregate(
        total_std=Sum('standard_hours'),
        total_extra=Sum('extra_time'),
        total_ot=Sum('overtime')
    )
    
    # Detailed logs
    logs = ProjectHours.objects.filter(project=project).select_related('employee').order_by('-date')
    
    context = {
        'project': project,
        'stats': stats,
        'logs': logs,
    }
    return render(request, 'projects/project_detail.html', context)
