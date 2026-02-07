from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class AuditLog(models.Model):
    """Custom audit trail for tracking all system actions"""
    
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Created'
        UPDATE = 'UPDATE', 'Updated'
        DELETE = 'DELETE', 'Deleted'
        LOGIN = 'LOGIN', 'Logged In'
        LOGOUT = 'LOGOUT', 'Logged Out'
        APPROVE = 'APPROVE', 'Approved'
        REJECT = 'REJECT', 'Rejected'
        EXPORT = 'EXPORT', 'Exported'
        IMPORT = 'IMPORT', 'Imported'
        VIEW = 'VIEW', 'Viewed'
    
    # Who did it
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='audit_logs'
    )
    
    # What was done
    action = models.CharField(max_length=20, choices=Action.choices)
    
    # What object was affected (Generic Foreign Key)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Details
    object_repr = models.CharField(max_length=200, blank=True, help_text="String representation of the object")
    changes = models.JSONField(null=True, blank=True, help_text="What changed (before/after)")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # When
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.object_repr} at {self.timestamp}"
    
    @classmethod
    def log(cls, user, action, obj=None, changes=None, request=None):
        """Helper method to create audit logs"""
        log_entry = cls(
            user=user,
            action=action,
            object_repr=str(obj)[:200] if obj else '',
            changes=changes
        )
        
        if obj:
            log_entry.content_type = ContentType.objects.get_for_model(obj)
            log_entry.object_id = obj.pk
        
        if request:
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                log_entry.ip_address = x_forwarded_for.split(',')[0]
            else:
                log_entry.ip_address = request.META.get('REMOTE_ADDR')
            
            # Get user agent
            log_entry.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        log_entry.save()
        return log_entry
