"""
Audit Logging Middleware for Nexteons HRMS
Automatically tracks all POST, PUT, PATCH, DELETE requests
"""
import json
from django.utils.deprecation import MiddlewareMixin
from django.contrib.contenttypes.models import ContentType
from core.models import AuditLog


class AuditLogMiddleware(MiddlewareMixin):
    """
    Middleware to automatically log all data-modifying requests
    """
    
    # Paths to exclude from logging
    EXCLUDED_PATHS = [
        '/admin/jsi18n/',
        '/static/',
        '/media/',
        '/__debug__/',
        '/leaves/leave-requests/add/',
        '/leaves/leave-requests/approve/',
        '/leaves/leave-requests/reject/',
        '/leaves/leave-requests/cancel/',
    ]
    
    # Models to exclude from automatic logging
    EXCLUDED_MODELS = [
        'session',
        'contenttype',
        'permission',
        'logentry',
        'auditlog',  # Don't log audit logs themselves
    ]
    
    def process_response(self, request, response):
        """
        Process the response and log if it was a data-modifying request
        """
        
        # Only log authenticated users
        if not request.user.is_authenticated:
            return response
        
        # Only log POST, PUT, PATCH, DELETE
        if request.method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return response
        
        # Skip excluded paths
        if any(request.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return response
        
        # Only log successful responses (2xx and 3xx)
        if response.status_code >= 400:
            return response
        
        # Try to log the action
        try:
            self._log_request(request, response)
        except Exception as e:
            # Don't break the request if logging fails
            print(f"Audit logging error: {e}")
        
        return response
    
    def _log_request(self, request, response):
        """
        Create an audit log entry for this request
        """
        path = request.path.lower()
        
        # Determine action based on method
        # Default to UPDATE for POST unless it's explicitly a creation path
        action_map = {
            'POST': AuditLog.Action.UPDATE, 
            'PUT': AuditLog.Action.UPDATE,
            'PATCH': AuditLog.Action.UPDATE,
            'DELETE': AuditLog.Action.DELETE,
        }
        
        # Check if it's a creation request based on standard URL patterns
        action = action_map.get(request.method, AuditLog.Action.UPDATE)
        if request.method == 'POST' and ('/add/' in path or '/create/' in path):
            action = AuditLog.Action.CREATE
        
        # Try to extract object information from the request
        obj = None
        changes = {}
        module = None
        
        # Detect module from URL path
        if '/payroll/' in path:
            module = AuditLog.Module.PAYROLL
        elif '/attendance/' in path:
            module = AuditLog.Module.ATTENDANCE
        elif '/leaves/' in path or '/leave' in path:
            module = AuditLog.Module.LEAVES
        elif '/employees/' in path or '/employee' in path:
            module = AuditLog.Module.EMPLOYEES
        elif '/users/' in path or '/user' in path or '/administration/' in path:
            module = AuditLog.Module.USERS
        elif '/documents/' in path:
            module = AuditLog.Module.DOCUMENTS
        elif '/ticket' in path:
            module = AuditLog.Module.TICKETS
        elif '/system-admin/' in path or '/company-profile/' in path:
            module = AuditLog.Module.SYSTEM
        
        # Try to capture form data for changes
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                # Get POST data
                post_data = request.POST.dict()
                
                # Remove sensitive/unnecessary fields
                excluded_fields = ['csrfmiddlewaretoken', 'password', 'password1', 'password2']
                changes = {k: v for k, v in post_data.items() if k not in excluded_fields and v}
                
                # Format as old_value/new_value structure
                if changes:
                    changes = {'new_values': changes}
                    
            except Exception:
                pass
        
        # Create object representation from path
        object_repr = f"{request.method} {request.path}"
        
        # Create the audit log
        AuditLog.log(
            user=request.user,
            action=action,
            obj=None,  # We don't have the actual object here
            changes=changes if changes else None,
            request=request,
            module=module
        )
