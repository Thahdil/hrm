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
    
    from core.utils.pagination import get_paginated_data
    paginator, page_obj = get_paginated_data(request, meetings, default_limit=10)
    
    return render(request, 'meetings/meeting_list.html', {
        'meetings': page_obj, 
        'paginator': paginator,
        'page_obj': page_obj,
        'is_paginated': True,
        'filter_type': filter_type
    })

@login_required
def schedule_meeting(request):
    """
    View to schedule a new meeting.
    All authenticated employees can schedule meetings.
    """

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
    users = User.objects.filter(is_active=True).exclude(is_superuser=True).exclude(role='ADMIN').exclude(pk=request.user.pk)
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
            'is_participant': request.user in meeting.participants.all(),
            'is_past': meeting.end_time < timezone.now()
        })
        
    return render(request, 'meetings/meeting_detail.html', {
        'meeting': meeting,
        'all_eligible_users': all_eligible_users,
        'current_participant_ids': list(participant_ids),
        'is_participant': request.user in meeting.participants.all(),
        'is_past': meeting.end_time < timezone.now()
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
        
    if meeting.end_time < timezone.now():
        messages.error(request, "Cannot modify participants for a past meeting.")
        return redirect('meeting_list')
        
    if request.method == 'POST':
        participant_ids = request.POST.getlist('participants')
        
        # Always ensure organizer is included in participants
        organizer_id = str(meeting.organizer.pk)
        if organizer_id not in participant_ids:
            participant_ids.append(organizer_id)
            
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
        
    if meeting.end_time < timezone.now():
        messages.error(request, "Cannot cancel a meeting that has already ended.")
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

@login_required
def meeting_edit(request, pk):
    """AJAX endpoint for editing specific fields of a meeting."""
    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'success': False, 'error': 'Invalid request method.'})

    meeting = get_object_or_404(Meeting, pk=pk)
    
    # Check permissions
    if request.user != meeting.organizer:
        from django.http import JsonResponse
        return JsonResponse({'success': False, 'error': 'You do not have permission to edit this meeting. Only the organizer can do this.'})

    if meeting.end_time < timezone.now():
        from django.http import JsonResponse
        return JsonResponse({'success': False, 'error': 'Cannot edit a past meeting.'})

    field_update = request.POST.get('field_update')
    from django.http import JsonResponse

    try:
        if field_update == 'title':
            new_title = request.POST.get('title', '').strip()
            if not new_title:
                return JsonResponse({'success': False, 'error': 'Title cannot be empty.'})
            meeting.title = new_title
        elif field_update == 'description':
            meeting.description = request.POST.get('description', '')
        else:
            return JsonResponse({'success': False, 'error': 'Invalid field update.'})

        meeting.save()
        
        # Log the activity
        from core.models import AuditLog
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            obj=meeting,
            changes={field_update: getattr(meeting, field_update)},
            request=request
        )

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
