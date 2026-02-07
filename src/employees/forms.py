from django import forms
from django.contrib.auth import get_user_model
from .models import DocumentVault

User = get_user_model()

class EmployeeForm(forms.ModelForm):
    # Encrypted fields
    pan_number = forms.CharField(required=False, label="PAN Card", widget=forms.TextInput(attrs={'class': 'form-input'}))
    passport_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-input'}))
    iban = forms.CharField(required=False, label="Bank Account Number", widget=forms.TextInput(attrs={'class': 'form-input'}))
    
    # Auth fields (since we are creating a User now)
    username = forms.CharField(required=True, label="Login ID", help_text="Unique Username", widget=forms.TextInput(attrs={'class': 'form-input'}))
    password = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'class': 'form-input'}), help_text="Leave blank to keep existing password if editing")

    class Meta:
        model = User
        fields = ['username', 'employee_id', 'email', 'full_name', 'phone_number', 'designation', 'department',
                  'date_of_joining', 'aadhaar_number', 'salary_basic', 'salary_allowance', 'status', 
                  'contract_type', 'ifsc_code', 'address', 'date_of_birth', 'gender']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. EMP-001'}),
            'full_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-input'}),
            'designation': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'salary_basic': forms.NumberInput(attrs={'class': 'form-input'}),
            'salary_allowance': forms.NumberInput(attrs={'class': 'form-input'}),
            'aadhaar_number': forms.TextInput(attrs={'class': 'form-input'}),
            'ifsc_code': forms.TextInput(attrs={'class': 'form-input'}),
            'address': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'employee_id': 'Employee ID',
            'username': 'Login ID',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import CompanySettings
        settings = CompanySettings.load()
        
        if self.instance.pk:
            self.fields['pan_number'].initial = self.instance.pan_number
            self.fields['passport_number'].initial = self.instance.passport_number
            self.fields['iban'].initial = self.instance.iban
            # Editing existing user
            self.fields['password'].required = False
            self.fields['username'].disabled = True # Prevent changing username
        else:
            # New Employee: Set default prefix
            self.fields['employee_id'].initial = settings.employee_id_prefix

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.pan_number = self.cleaned_data['pan_number']
        instance.passport_number = self.cleaned_data['passport_number']
        instance.iban = self.cleaned_data['iban']
        
        # Apply Employee ID Prefix logic
        from core.models import CompanySettings
        settings = CompanySettings.load()
        prefix = settings.employee_id_prefix
        emp_id = self.cleaned_data.get('employee_id')
        
        if emp_id and prefix and not emp_id.startswith(prefix):
            # If user only entered a number, prepend the prefix
            instance.employee_id = f"{prefix}{emp_id}"
        elif emp_id:
            instance.employee_id = emp_id
        
        # Handle Password
        password = self.cleaned_data.get('password')
        if password:
            instance.set_password(password)
            
        # Ensure role is EMPLOYEE (if not set otherwise)
        if not instance.role:
            instance.role = 'EMPLOYEE'

        if commit:
            instance.save()
        return instance

class DocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentVault
        fields = ['employee', 'document_type', 'file', 'issue_date', 'expiry_date']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.FileInput(attrs={'class': 'form-input-file'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(DocumentForm, self).__init__(*args, **kwargs)
        
        # Enforce issue and expiry dates as required
        self.fields['issue_date'].required = True
        self.fields['expiry_date'].required = True
        if 'employee' in self.fields:
            # Only show users with the EMPLOYEE role
            self.fields['employee'].queryset = User.objects.filter(role='EMPLOYEE').order_by('full_name')
            self.fields['employee'].label_from_instance = lambda obj: f"{obj.full_name or obj.username.title()} ({obj.employee_id or 'No ID'})"
        
        # If user is not Admin, hide employee selection
        if self.user and not (self.user.is_staff or (hasattr(self.user, 'role') and self.user.role in ['ADMIN', 'CEO'])):
            if 'employee' in self.fields:
                del self.fields['employee']
