from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'full_name', 'email', 'role', 'additional_role', 'managers', 'is_active')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'full_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'additional_role': forms.Select(attrs={'class': 'form-select'}),
            'managers': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        manager_roles = ['CEO', 'PROJECT_MANAGER']
        
        self.fields['managers'].queryset = User.objects.filter(
            Q(role__in=manager_roles) | 
            Q(additional_role__in=manager_roles)
        ).order_by('full_name', 'username')
        
        self.fields['managers'].label_from_instance = lambda obj: f"{obj.full_name or obj.username.upper()} ({obj.get_role_display()})"

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            self.save_m2m()
        return user

class CustomUserChangeForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}), required=False, help_text="Leave blank to keep current password")

    class Meta:
        model = User
        fields = ('username', 'full_name', 'email', 'role', 'additional_role', 'managers', 'is_active', 'password')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'full_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'additional_role': forms.Select(attrs={'class': 'form-select'}),
            'managers': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        # Define roles that can be managers
        manager_roles = ['CEO', 'PROJECT_MANAGER']
        
        # Filter queryset
        self.fields['managers'].queryset = User.objects.filter(
            Q(role__in=manager_roles) | 
            Q(additional_role__in=manager_roles)
        ).exclude(pk=self.instance.pk).order_by('full_name', 'username')
        
        # Custom display label for dropdown
        self.fields['managers'].label_from_instance = lambda obj: f"{obj.full_name or obj.username.upper()} ({obj.get_role_display()})"

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user
