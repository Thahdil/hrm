from django import forms

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Enter your registered email'}))

class OTPVerifyForm(forms.Form):
    otp = forms.CharField(max_length=6, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Enter 6-digit OTP', 'style': 'letter-spacing: 4px; font-weight: bold; text-align: center;'}))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'New Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm Password'}))

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password")
        p2 = cleaned_data.get("confirm_password")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
