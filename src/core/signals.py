"""
Signal handlers for automatic audit logging
Tracks model-level changes with old/new value comparison
"""
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from core.models import AuditLog
import threading

# Thread-local storage for tracking old values
_thread_locals = threading.local()


def get_current_request():
    """Get the current request from thread-local storage"""
    return getattr(_thread_locals, 'request', None)


def set_current_request(request):
    """Store the current request in thread-local storage"""
    _thread_locals.request = request


class CurrentRequestMiddleware:
    """Middleware to store current request in thread-local storage"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        set_current_request(request)
        response = self.get_response(request)
        set_current_request(None)
        return response


def get_model_changes(instance, old_instance=None):
    """
    Compare old and new instance values to track changes
    Returns a dict of {field_name: {'old': old_value, 'new': new_value}}
    """
    if not old_instance:
        return None
    
    changes = {}
    for field in instance._meta.fields:
        field_name = field.name
        
        # Skip these fields
        if field_name in ['id', 'created_at', 'updated_at', 'password']:
            continue
        
        old_value = getattr(old_instance, field_name, None)
        new_value = getattr(instance, field_name, None)
        
        # Only log if value changed
        if old_value != new_value:
            changes[field_name] = {
                'old': str(old_value) if old_value is not None else None,
                'new': str(new_value) if new_value is not None else None
            }
    
    return changes if changes else None


# Store old instance before save
@receiver(pre_save)
def store_old_instance(sender, instance, **kwargs):
    """Store the old instance before save for comparison"""
    
    # Skip audit log model itself
    if sender.__name__ == 'AuditLog':
        return
    
    # Skip if this is a new instance
    if not instance.pk:
        return
    
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        instance._old_instance = old_instance
    except sender.DoesNotExist:
        pass


# Log after save
@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """Automatically log model saves"""
    
    # Skip certain models or internal technical records
    model_name = sender.__name__.lower()
    excluded = ['session', 'contenttype', 'permission', 'logentry', 'auditlog', 'migration', 'leavebalance', 'leavetype', 'rawpunch', 'attendancelog']
    if any(ex in model_name for ex in excluded):
        return
    
    request = get_current_request()
    user = request.user if request and request.user.is_authenticated else None
    
    if not user:
        return  # Only log if we have a user
    
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    
    # Get changes if this was an update
    changes = None
    if not created and hasattr(instance, '_old_instance'):
        changes = get_model_changes(instance, instance._old_instance)
        
        # Smart action detection (e.g. for approvals)
        if changes and 'status' in changes:
            new_status = changes['status'].get('new', '').upper()
            if 'APPROVED' in new_status:
                action = AuditLog.Action.APPROVE
            elif 'REJECTED' in new_status:
                action = AuditLog.Action.REJECT
            elif 'CANCELLED' in new_status:
                action = AuditLog.Action.CANCELLED
    
    # Log the action
    try:
        AuditLog.log(
            user=user,
            action=action,
            obj=instance,
            changes=changes,
            request=request
        )
    except Exception as e:
        print(f"Error logging save: {e}")


# Log after delete
@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """Automatically log model deletions"""
    
    # Skip certain models
    model_name = sender.__name__.lower()
    excluded = ['session', 'contenttype', 'permission', 'logentry', 'auditlog', 'migration', 'leavebalance', 'leavetype']
    if any(ex in model_name for ex in excluded):
        return
    
    request = get_current_request()
    user = request.user if request and request.user.is_authenticated else None
    
    if not user:
        return
    
    # Log the deletion
    try:
        AuditLog.log(
            user=user,
            action=AuditLog.Action.DELETE,
            obj=instance,
            changes=None,
            request=request
        )
    except Exception as e:
        print(f"Error logging delete: {e}")
