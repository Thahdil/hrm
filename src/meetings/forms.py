from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Meeting
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class MeetingForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).exclude(is_superuser=True).exclude(role='ADMIN').order_by('first_name', 'last_name', 'username'),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8'}),
        help_text="Hold Ctrl/Cmd to select multiple participants"
    )
    
    # Separate Date and Time Fields
    meeting_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text="Date of the meeting"
    )
    start_time_input = forms.TimeField(
        widget=forms.TextInput(attrs={'class': 'form-control time-input', 'placeholder': 'Start Time', 'autocomplete': 'off', 'readonly': 'readonly'}),
        input_formats=['%I:%M %p', '%I:%M%p', '%H:%M'],
        help_text="Start Time"
    )
    end_time_input = forms.TimeField(
        widget=forms.TextInput(attrs={'class': 'form-control time-input', 'placeholder': 'End Time', 'autocomplete': 'off', 'readonly': 'readonly'}),
        input_formats=['%I:%M %p', '%I:%M%p', '%H:%M'],
        help_text="End Time"
    )

    class Meta:
        model = Meeting
        fields = ['title', 'description', 'participants', 'room'] # Excludes start_time/end_time as we handle them manually
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Meeting Title', 'autocomplete': 'off'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Agenda / Description'}),
            'room': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional Room/Location'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Populate initial values for split fields if editing
        if self.instance and self.instance.pk:
            from django.utils import timezone
            current_tz = timezone.get_current_timezone()
            
            # Convert to local time for correct display in form
            start_local = self.instance.start_time.astimezone(current_tz)
            end_local = self.instance.end_time.astimezone(current_tz)
            
            self.fields['meeting_date'].initial = start_local.date()
            self.fields['start_time_input'].initial = start_local.strftime('%I:%M %p')
            self.fields['end_time_input'].initial = end_local.strftime('%I:%M %p')

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('meeting_date')
        start_t = cleaned_data.get('start_time_input')
        end_t = cleaned_data.get('end_time_input')
        participants = cleaned_data.get('participants')

        if not (date and start_t and end_t):
            return

        # Combine into datetimes
        from django.utils import timezone
        import datetime
        
        # Create naive datetimes first
        start_dt_naive = datetime.datetime.combine(date, start_t)
        end_dt_naive = datetime.datetime.combine(date, end_t)
        
        # Make valid timezone aware
        start = timezone.make_aware(start_dt_naive)
        end = timezone.make_aware(end_dt_naive)
        
        # Handle overnight meetings (if end time is before start time, assume next day? 
        # For now, strict same-day policy as requested implicitly by single date field, 
        # but let's just validations error if end < start on same day)
        if end <= start:
            raise ValidationError("End time must be after start time.")
        
        if start < timezone.now():
            raise ValidationError("Cannot schedule meetings in the past.")

        # Save for use in save() method
        self.cleaned_data['start_time'] = start
        self.cleaned_data['end_time'] = end

        conflicts = []

        # 1. Check Organizer (Request User) Availability
        if self.user:
            busy_as_participant = Meeting.objects.filter(participants=self.user).filter(
                start_time__lt=end,
                end_time__gt=start
            )
            
            if self.instance and self.instance.pk:
                 busy_as_participant = busy_as_participant.exclude(pk=self.instance.pk)
            
            if busy_as_participant.exists():
                 raise ValidationError("You (Organizer) are already booked for another meeting during this time.")

        # 2. Check Participants Availability
        if participants:
            for person in participants:
                qs = Meeting.objects.filter(participants=person).filter(
                    start_time__lt=end,
                    end_time__gt=start
                )
                
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                
                if qs.exists():
                    conflicts.append(f"{person.get_full_name() or person.username}")

        if conflicts:
            conflict_names = ", ".join(conflicts)
            raise ValidationError(f"The following participants are already booked during this time slot: {conflict_names}")

        return cleaned_data

    def save(self, commit=True):
        meeting = super().save(commit=False)
        # Manually assign the computed datetimes
        meeting.start_time = self.cleaned_data.get('start_time')
        meeting.end_time = self.cleaned_data.get('end_time')
        
        if commit:
            meeting.save()
            self.save_m2m()
        return meeting
