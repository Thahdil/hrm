from django import forms
from django.contrib.auth import get_user_model
from .models import AttendanceLog

User = get_user_model()

class AttendanceImportForm(forms.Form):
    file = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-input-file'}), help_text="Upload CSV or Excel (.xlsx) file")

class AttendanceManualEntryForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).exclude(role='CEO').exclude(is_superuser=True).exclude(username='admin').order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    start_date = forms.DateField(
        label="From Date",
        widget=forms.DateInput(attrs={
            'class': 'form-input', 
            'type': 'date', 
            'id': 'manual_start_date',
            'onclick': 'this.showPicker()'
        })
    )
    days = forms.IntegerField(
        label="Number of Days",
        initial=1,
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'id': 'manual_days'})
    )
    end_date = forms.DateField(
        label="To Date",
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-input', 
            'type': 'date', 
            'id': 'manual_end_date',
            'onclick': 'this.showPicker()'
        })
    )
    work_duration = forms.DecimalField(
        label="Work Duration (Hours)",
        initial=8.0,
        min_value=0,
        max_value=24,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'id': 'manual_work_duration', 'step': '0.5'})
    )
    REASON_CHOICES = [
        ('WFH', 'Work from Home'),
        ('Field Work', 'Field Work'),
        ('Other', 'Other')
    ]
    reason_type = forms.ChoiceField(
        choices=REASON_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'manual_reason_type'})
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'id': 'manual_remarks'}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].label_from_instance = lambda obj: obj.full_name or obj.username.title()
    
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        days = cleaned_data.get('days')
        end = cleaned_data.get('end_date')
        reason_type = cleaned_data.get('reason_type')
        remarks = cleaned_data.get('remarks')

        if reason_type == 'Other' and not remarks:
            self.add_error('remarks', "Remarks are required when 'Other' reason is selected.")

        if start and days and not end:
            from datetime import timedelta
            end = start + timedelta(days=days - 1)
            cleaned_data['end_date'] = end
            
        elif start and end:
            if start > end:
                self.add_error('end_date', "End date cannot be before start date.")
            else:
                cleaned_data['days'] = (end - start).days + 1

        return cleaned_data

from .models import ManualPunchRequest

class ManualPunchRequestForm(forms.ModelForm):
    REASON_CHOICES = [
        ('', 'Select a reason...'),
        ('WFH', 'Work from Home'),
        ('Field Work', 'Field Work'),
        ('Other', 'Other')
    ]
    reason_type = forms.ChoiceField(
        choices=REASON_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'req_reason_type', 'onchange': 'toggleOtherReason()'})
    )

    punch_in_time = forms.TimeField(
        widget=forms.TextInput(attrs={'class': 'form-input time-input', 'placeholder': '--:-- --', 'readonly': 'readonly'}),
        input_formats=['%I:%M %p', '%I:%M%p', '%H:%M']
    )
    punch_out_time = forms.TimeField(
        widget=forms.TextInput(attrs={'class': 'form-input time-input', 'placeholder': '--:-- --', 'readonly': 'readonly'}),
        input_formats=['%I:%M %p', '%I:%M%p', '%H:%M']
    )

    class Meta:
        model = ManualPunchRequest
        fields = ['date', 'punch_in_time', 'punch_out_time', 'reason']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input', 'id': 'req_date', 'onclick': 'this.showPicker()'}),
            'reason': forms.Textarea(attrs={
                'class': 'form-textarea', 
                'rows': 3, 
                'id': 'req_reason_other', 
                'placeholder': 'Please provide details...',
                'style': 'display: none;'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['reason'].required = False

    def clean(self):
        cleaned_data = super().clean()
        reason_type = cleaned_data.get('reason_type')
        reason_text = cleaned_data.get('reason')
        date = cleaned_data.get('date')

        if date:
            from django.utils import timezone
            import datetime
            today = timezone.localdate()
            yesterday = today - datetime.timedelta(days=1)
            
            # Allow managers to bypass date restrictions
            can_bypass_date = False
            if self.user:
                if self.user.is_staff or getattr(self.user, 'role', '') in ['CEO', 'PROJECT_MANAGER', 'ADMIN', 'HR_MANAGER']:
                    can_bypass_date = True
            
            if not can_bypass_date:
                if date > today:
                    self.add_error('date', "Cannot submit manual punch for future dates.")
                elif date < yesterday:
                    self.add_error('date', "Manual punch requests must be submitted by the next day (only today and yesterday are allowed).")

        if reason_type == 'Other':
            if not reason_text:
                self.add_error('reason', "Please provide details for the 'Other' reason.")
        elif reason_type:
            # Map choice description or key to the reason field
            choices_dict = dict(self.REASON_CHOICES)
            cleaned_data['reason'] = choices_dict.get(reason_type)

        return cleaned_data
