from django.contrib.auth.views import LoginView, LogoutView
from core.models import AuditLog


from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CustomLoginView(LoginView):
    """Custom login view with audit logging"""
    template_name = 'login.html'
    
    def form_valid(self, form):
        """Log successful login"""
        response = super().form_valid(form)
        
        # Log the login
        AuditLog.log(
            user=self.request.user,
            action=AuditLog.Action.LOGIN,
            obj=None,
            changes=None,
            request=self.request,
            module=AuditLog.Module.SYSTEM
        )
        
        return response


class CustomLogoutView(LogoutView):
    """Custom logout view with audit logging"""
    
    def dispatch(self, request, *args, **kwargs):
        """Log logout before actually logging out"""
        if request.user.is_authenticated:
            # Log the logout
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.LOGOUT,
                obj=None,
                changes=None,
                request=request,
                module=AuditLog.Module.SYSTEM
            )
        
        return super().dispatch(request, *args, **kwargs)
