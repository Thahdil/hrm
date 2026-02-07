from django import forms
from .models import CompanySettings, PublicHoliday

class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = [
            'name', 'address', 'website', 'employee_id_prefix', 'pan_number', 'gstin', 'tan_number', 'logo',
            'work_monday', 'work_tuesday', 'work_wednesday', 'work_thursday', 
            'work_friday', 'work_saturday', 'work_sunday'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'address': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'website': forms.URLInput(attrs={'class': 'form-input'}),
            'employee_id_prefix': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. EMP-'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ABCDE1234F'}),
            'gstin': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '15-digit GST Number'}),
            'tan_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ABCD12345E'}),
        }

class PublicHolidayForm(forms.ModelForm):
    class Meta:
        model = PublicHoliday
        fields = ['name', 'date', 'is_recurring']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Holiday Name'}),
            'date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-checkbox'})
        }
