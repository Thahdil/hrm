from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .forms_assignment import EmployeeAssignmentForm
from django.contrib.auth import get_user_model, login
from django.contrib.auth import login as auth_login

User = get_user_model()

@login_required
def user_list(request):
    if not request.user.is_staff and request.user.role not in ['ADMIN', 'CEO', 'HR_MANAGER']:
        messages.error(request, "Access Denied")
        return redirect('dashboard')
        
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'users/user_list.html', {'users': users})

@login_required
def user_create(request):
    if not request.user.is_staff and request.user.role not in ['ADMIN', 'CEO']:
        messages.error(request, "Access Denied")
        return redirect('dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "User account created successfully.")
            return redirect('user_list')
    else:
        form = CustomUserCreationForm()
    return render(request, 'users/user_form.html', {
        'form': form,
        'title': 'Create New User',
        'button_text': 'Create Account'
    })

@login_required
def user_edit(request, pk):
    if not request.user.is_staff and request.user.role not in ['ADMIN', 'CEO']:
        messages.error(request, "Access Denied")
        return redirect('dashboard')
        
    user_obj = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"User {user_obj.username} updated successfully.")
            return redirect('user_list')
    else:
        form = CustomUserChangeForm(instance=user_obj)
        
    return render(request, 'users/user_form.html', {
        'form': form,
        'title': f'Edit User: {user_obj.username}',
        'button_text': 'Update User'
    })

@login_required
def manage_team_assignments(request):
    """View for project managers to assign employees under them"""
    # Check if user is a project manager
    if not request.user.is_project_manager():
        messages.error(request, "Access Denied. Only Project Managers can access this page.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = EmployeeAssignmentForm(request.POST, manager=request.user)
        if form.is_valid():
            selected_employees = form.cleaned_data['employees']
            
            # Get current subordinates of this manager
            current_subordinates = User.objects.filter(managers=request.user)
            
            # Remove this manager from those no longer selected
            for sub in current_subordinates:
                if sub not in selected_employees:
                    sub.managers.remove(request.user)
            
            # Add this manager to all selected employees
            for employee in selected_employees:
                employee.managers.add(request.user)
            
            messages.success(request, f"Successfully updated team assignments. {selected_employees.count()} employee(s) are now in your team.")
            return redirect('manage_team_assignments')
    else:
        form = EmployeeAssignmentForm(manager=request.user)
    
    # Get currently assigned employees (those who have this user in their managers list)
    assigned_employees = User.objects.filter(managers=request.user)
    
    # Create designation map for the template
    designation_map = {str(user.id): user.get_designation_display() for user in form.fields['employees'].queryset}
    
    context = {
        'form': form,
        'assigned_employees': assigned_employees,
        'total_assigned': assigned_employees.count(),
        'designation_map': designation_map
    }
    
    return render(request, 'users/team_assignments.html', context)

from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash

@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Important to update the session hash so the user doesn't get logged out
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'users/password_change.html', {
        'form': form,
        'title': 'Change Password',
        'button_text': 'Update Password'
    })
