from django import forms
from .models import LeaveRequest, LeaveType
from .models import TicketRequest

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'half_day', 'half_day_session', 'reason', 'assigned_manager']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'half_day': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'half_day_session': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'assigned_manager': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        User = get_user_model()
        
        # Enforce Active Leave Types by default (View will further refine this)
        self.fields['leave_type'].queryset = LeaveType.objects.filter(is_active=True)
        
        # Filter assigned_manager based on user's assigned managers ONLY
        if self.user and hasattr(self.user, 'managers'):
            user_managers = self.user.managers.all()
            self.fields['assigned_manager'].queryset = user_managers
            
            manager_count = user_managers.count()
            if manager_count == 1:
                # Single manager assigned - Pre-select and Read Only
                manager = user_managers.first()
                self.fields['assigned_manager'].initial = manager
                self.fields['assigned_manager'].disabled = True
                self.fields['assigned_manager'].help_text = "Your request will be processed by your assigned manager."
            elif manager_count > 1:
                # Multiple managers assigned - Employee MUST select one
                self.fields['assigned_manager'].help_text = "Please select which of your multiple assigned managers should approve this."
            else:
                # Zero managers assigned - Show warning and disable field
                self.fields['assigned_manager'].queryset = User.objects.none()
                self.fields['assigned_manager'].disabled = True
                self.fields['assigned_manager'].required = False
                self.fields['assigned_manager'].help_text = "⚠️ You have not been assigned to any manager yet. Please contact HR."
        else:
            self.fields['assigned_manager'].queryset = User.objects.none()
            self.fields['assigned_manager'].disabled = True

        self.fields['assigned_manager'].label = "Assign Manager"
        self.fields['assigned_manager'].label_from_instance = lambda obj: obj.full_name or obj.username.title()

        # Embed duration info into the Select widget choices for JS to use
        # We can't strictly add data-attributes to <option> from here easily without a custom widget.
        # Alternatively, we can rely on passing a JSON object to the template, but let's try 
        # to just iterate over the queryset and populate it in the template via a context variable if possible, 
        # or simplified: just let the view handle passing the leave types with duration.
        # But we are in the form `__init__`.
        # Simplest approach for JS: We will render a JS object in the template, not here.

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        leave_type = cleaned_data.get('leave_type')
        half_day = cleaned_data.get('half_day')
        half_day_session = cleaned_data.get('half_day_session')

        if start_date and leave_type:
            # Backend Logic for validation:
            
            # Half Day Logic
            if half_day:
                if not half_day_session:
                    self.add_error('half_day_session', 'Please select Morning or Afternoon for half-day leave.')
                
                # Check if this leave type allows half day
                if hasattr(leave_type, 'allow_half_day') and not leave_type.allow_half_day:
                     self.add_error('half_day', f'{leave_type.name} does not allow half-day requests.')
                
                # For half day, end date is effectively ignored/reset to start date
                # So we don't need to validate it strictly if missing
            else:
                # Normal Full Day Logic
                if hasattr(leave_type, 'duration_days') and leave_type.duration_days:
                     # If Fixed Duration, we effectively ignore the user's end date input for validation purposes 
                     # because the model will overwrite it.
                     pass
                else:
                     # For manual duration (Sick Leave), End Date IS required.
                     if not end_date:
                         self.add_error('end_date', 'End date is required for this leave type.')
                     elif end_date < start_date:
                         self.add_error('end_date', 'End date cannot be before start date.')
            
            # 2. Duration Check (Generic Max Entitlement) - Only if end_date valid or calculable
            # We skip this here to keep it simple or implement if needed. 
            pass
            
        return cleaned_data

class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ['name', 'code', 'days_entitlement', 'duration_days', 'eligibility_gender', 'min_service_days', 'is_paid', 'is_carry_forward', 'reset_monthly', 'allow_unlimited', 'hidden_unless_used', 'allow_half_day', 'requires_document']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'code': forms.TextInput(attrs={'class': 'form-input'}),
            'days_entitlement': forms.NumberInput(attrs={'class': 'form-input'}),
            'duration_days': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Optional: e.g. 1 or 30'}),
            'eligibility_gender': forms.Select(attrs={'class': 'form-select'}),
            'min_service_days': forms.NumberInput(attrs={'class': 'form-input'}),
            'is_paid': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'is_carry_forward': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'reset_monthly': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'allow_unlimited': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'hidden_unless_used': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'allow_half_day': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make code optional in the UI since we auto-generate it
        self.fields['code'].required = False

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        code = cleaned_data.get('code')
        
        # Auto-generate code if missing
        if name and not code:
            # First try abbreviation (e.g. "Annual Leave" -> "AL")
            words = name.split()
            if len(words) > 1:
                base_code = "".join([w[0] for w in words]).upper()
            else:
                base_code = name[:3].upper() # "Holiday" -> "HOL"
            
            # Ensure uniqueness
            final_code = base_code
            counter = 1
            while LeaveType.objects.filter(code=final_code).exclude(pk=self.instance.pk).exists():
                final_code = f"{base_code}-{counter:02d}"
                counter += 1
            
            cleaned_data['code'] = final_code
            
        return cleaned_data
