from django import forms
from django.contrib.auth import get_user_model
from .models import AttendanceLog

User = get_user_model()

class AttendanceImportForm(forms.Form):
    file = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-input-file'}), help_text="Upload CSV or Excel (.xlsx) file")

class AttendanceManualEntryForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).exclude(role='CEO').exclude(is_superuser=True).exclude(username='admin').order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'})
    )
    check_in = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
        required=False
    )
    check_out = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
        required=False
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
        required=True # User said "justification", implies required? Making it required to be safe, or per manual entry strictness. But 'required' in model is False. Let's make it True for manual.
    )

    class Meta:
        model = AttendanceLog
        fields = ['employee', 'date', 'status', 'check_in', 'check_out', 'remarks']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].label_from_instance = lambda obj: obj.full_name or obj.username.title()
    
    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        date = cleaned_data.get('date')
        
        # Check for existing log
        if employee and date:
            if AttendanceLog.objects.filter(employee=employee, date=date).exists():
                raise forms.ValidationError("Attendance log already exists for this employee on this date.")
        
        return cleaned_data
