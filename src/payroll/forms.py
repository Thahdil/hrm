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
