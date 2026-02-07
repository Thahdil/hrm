from django import forms
from users.models import CustomUser

class EmployeeAssignmentForm(forms.Form):
    """Form for project managers to assign employees under them"""
    employees = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(
            role=CustomUser.Role.EMPLOYEE,
            status=CustomUser.Status.ACTIVE
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select Employees to Assign"
    )
    
    def __init__(self, *args, **kwargs):
        manager = kwargs.pop('manager', None)
        super().__init__(*args, **kwargs)
        
        if manager:
            # Pre-select employees already assigned to this manager
            assigned_employees = CustomUser.objects.filter(managers=manager)
            self.fields['employees'].initial = assigned_employees
