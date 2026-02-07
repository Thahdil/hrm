from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from .models_otp import OTPToken
from .forms_otp import PasswordResetRequestForm, OTPVerifyForm

User = get_user_model()

def password_reset_request(request):
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                token = OTPToken.generate(user)
                
                # --- SEND REAL EMAIL ---
                from django.core.mail import send_mail
                from django.conf import settings
                
                subject = "Password Reset OTP - Nexteons HR"
                message = f"""
Hello {user.username},

You requested to reset your password.
Your OTP is: {token.token}

This code expires in 10 minutes.

If you did not request this, please ignore this email.
"""
                try:
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
                    messages.success(request, f"OTP sent to {email}.")
                except Exception as e:
                     # Fallback for dev if SMTP fails
                     print(f"SMTP Error: {e}")
                     print(f"[DEV FALLBACK] OTP for {email}: {token.token}")
                     messages.warning(request, f"Could not send email (SMTP Error). OTP printed to console for testing.")
                
                request.session['reset_email'] = email
                return redirect('password_reset_verify')
            except User.DoesNotExist:
                # Security: Don't reveal user doesn't exist, just say sent
                messages.success(request, f"If an account exists for {email}, an OTP has been sent.")
                return redirect('login') 
    else:
        form = PasswordResetRequestForm()
    return render(request, 'users/password_reset_request.html', {'form': form})

def password_reset_verify(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('password_reset_request')

    if request.method == 'POST':
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            otp_input = form.cleaned_data['otp']
            new_password = form.cleaned_data['new_password']
            
            try:
                user = User.objects.get(email=email)
                latest_token = OTPToken.objects.filter(user=user, is_used=False).order_by('-created_at').first()
                
                if latest_token and latest_token.is_valid() and latest_token.token == otp_input:
                    # Success
                    user.set_password(new_password)
                    user.save()
                    latest_token.is_used = True
                    latest_token.save()
                    
                    del request.session['reset_email']
                    messages.success(request, "Password reset successfully. You can now login.")
                    return redirect('login')
                else:
                    messages.error(request, "Invalid or expired OTP.")
            except User.DoesNotExist:
                messages.error(request, "User not found.")
    else:
        form = OTPVerifyForm()
    
    return render(request, 'users/password_reset_verify.html', {'form': form, 'email': email})
