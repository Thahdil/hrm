from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Meeting
from .forms import MeetingForm
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def meeting_list(request):
    """
    Displays a list of meetings where the user is either the organizer or a participant.
    Also handles a basic calendar view integration if template supports it.
    """
    user = request.user
    today = timezone.now()
    
    # Filter: Upcoming vs Past
    filter_type = request.GET.get('filter', 'upcoming')
    
    base_qs = Meeting.objects.filter(
        Q(organizer=user) | Q(participants=user)
    ).distinct()
    
    if filter_type == 'past':
        meetings = base_qs.filter(end_time__lt=today).order_by('-start_time')
    else:
        meetings = base_qs.filter(end_time__gte=today).order_by('start_time')
    
    return render(request, 'meetings/meeting_list.html', {
        'meetings': meetings, 
        'filter_type': filter_type
    })

@login_required
def schedule_meeting(request):
    """
    View to schedule a new meeting.
    Restricted to CEO and Project Manager roles.
    """
    if not (request.user.is_ceo() or request.user.is_project_manager()):
        messages.error(request, "Only CEOs and Project Managers can schedule meetings.")
        return redirect('meeting_list')

    if request.method == 'POST':
        form = MeetingForm(request.POST, user=request.user)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.organizer = request.user
            meeting.save()
            
            # Save ManyToMany data (participants)
            form.save_m2m()
            
            # Ensure organizer is also a participant to block their calendar
            meeting.participants.add(request.user)
            
            # Log the activity
            from core.models import AuditLog
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                obj=meeting,
                changes={'start_time': meeting.start_time.strftime("%d %b %Y, %H:%M")},
                request=request
            )
            
            messages.success(request, f"Meeting '{meeting.title}' scheduled successfully.")
            return redirect('meeting_list')
    else:
        form = MeetingForm(user=request.user)
    
    # Create a mapping of user ID to Role Display for the frontend
    # This is to show correct roles in the participant list instead of "Employee" for everyone
    users = User.objects.filter(is_active=True).exclude(is_superuser=True).exclude(role='ADMIN')
    participant_roles = {user.pk: user.get_role_display() for user in users}

    return render(request, 'meetings/meeting_form.html', {
        'form': form, 
        'participant_roles': participant_roles
    })

@login_required
def meeting_detail(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    # Check permission
    if request.user != meeting.organizer and request.user not in meeting.participants.all():
        messages.error(request, "You do not have permission to view this meeting.")
    from django.db.models import Case, When, Value, IntegerField
    
    # Get currently invited participants
    participant_ids = meeting.participants.all().values_list('pk', flat=True)
    
    # Get all eligible users, sorted so that currently joined ones are at the top
    all_eligible_users = User.objects.filter(is_active=True).exclude(
        Q(pk=meeting.organizer.pk) |
        Q(is_superuser=True) |
        Q(role='ADMIN')
    ).annotate(
        is_selected=Case(
            When(pk__in=participant_ids, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by('-is_selected', 'first_name')
        
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
        return render(request, 'meetings/includes/meeting_detail_content.html', {
            'meeting': meeting,
            'all_eligible_users': all_eligible_users,
            'current_participant_ids': list(participant_ids),
            'is_participant': request.user in meeting.participants.all()
        })
        
    return render(request, 'meetings/meeting_detail.html', {
        'meeting': meeting,
        'all_eligible_users': all_eligible_users,
        'current_participant_ids': list(participant_ids),
        'is_participant': request.user in meeting.participants.all()
    })

@login_required
def add_participants(request, pk):
    """View to add new participants to an existing meeting."""
    meeting = get_object_or_404(Meeting, pk=pk)
    
    # Only organizer or current participants can add people
    is_participant = request.user in meeting.participants.all()
    if request.user != meeting.organizer and not is_participant:
        messages.error(request, "You do not have permission to add participants.")
        return redirect('meeting_list')
        
    if request.method == 'POST':
        participant_ids = request.POST.getlist('participants')
        # Use set to sync participants (adds new ones and removes unselected ones)
        meeting.participants.set(participant_ids)
        
        # Create a log entry for the update
        from core.models import AuditLog
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            obj=meeting,
            changes={'participants_count': len(participant_ids)},
            request=request
        )
        messages.success(request, "Participant list updated successfully.")
        if not participant_ids:
            messages.warning(request, "No participants were selected.")
            
    # Redirect back to where we came from
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'meeting_list'
    return redirect(next_url)

@login_required
def meeting_delete(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if request.user != meeting.organizer:
        messages.error(request, "Only the organizer can cancel this meeting.")
        return redirect('meeting_list')
        
    if request.method == 'POST':
        # Log the activity before deletion
        from core.models import AuditLog
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.DELETE,
            obj=meeting,
            request=request
        )
        meeting.delete()
        messages.success(request, "Meeting cancelled.")
        return redirect('meeting_list')
        
    return render(request, 'meetings/meeting_confirm_delete.html', {'meeting': meeting})
