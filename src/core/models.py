from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class CompanySettings(models.Model):
    name = models.CharField(max_length=100, default="Nexteons")
    address = models.TextField(blank=True)
    website = models.URLField(blank=True, help_text="Used in email footers")
    employee_id_prefix = models.CharField(max_length=10, default="EMP-", help_text="Default prefix for new employees (e.g. EMP-)")
    
    # Indian Specifics
    pan_number = models.CharField(max_length=50, blank=True, verbose_name="PAN Number", help_text="Permanent Account Number")
    gstin = models.CharField(max_length=50, blank=True, verbose_name="GSTIN", help_text="GST Identification Number")
    tan_number = models.CharField(max_length=50, blank=True, verbose_name="TAN Number", help_text="Tax Deduction Account Number")
    
    # Working Days Configuration
    work_monday = models.BooleanField(default=True)
    work_tuesday = models.BooleanField(default=True)
    work_wednesday = models.BooleanField(default=True)
    work_thursday = models.BooleanField(default=True)
    work_friday = models.BooleanField(default=True)
    work_saturday = models.BooleanField(default=True) # Working by default, but 2nd Sat might be holiday
    work_sunday = models.BooleanField(default=False)
    second_saturday_holiday = models.BooleanField(default=True)

    # Financials
    currency_symbol = models.CharField(max_length=10, default="₹")
    currency_code = models.CharField(max_length=10, default="INR")

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        ARCHIVED = "ARCHIVED", "Archived"
        PENDING = "PENDING", "Pending"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    # Branding
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    
    # Cache singleton
    def save(self, *args, **kwargs):
        self.pk = 1 # Force singleton
        super(CompanySettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.name

    def is_holiday(self, check_date):
        """
        Logic to determine if a given date is a holiday based on settings.
        Handles fixed working/non-working days, Sundays, and 2nd Saturday.
        """
        # 1. Check Public Holidays first
        if PublicHoliday.objects.filter(date=check_date).exists():
            return True
        
        # Check recurring public holidays (month/day match)
        if PublicHoliday.objects.filter(is_recurring=True, date__month=check_date.month, date__day=check_date.day).exists():
            return True

        # 2. Check Sundays (Default Holiday)
        if check_date.weekday() == 6: # Sunday
            return not self.work_sunday # Usually True
            
        # 3. Check Saturday & 2nd Saturday
        if check_date.weekday() == 5: # Saturday
            # Is it the 2nd Saturday? (Day between 8 and 14)
            is_second_sat = 8 <= check_date.day <= 14
            if is_second_sat and self.second_saturday_holiday:
                return True
            return not self.work_saturday

        # 4. Check other weekday overrides
        days = [
            self.work_monday, self.work_tuesday, self.work_wednesday, 
            self.work_thursday, self.work_friday
        ]
        if not days[check_date.weekday()]:
            return True

        return False

class PublicHoliday(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()
    is_recurring = models.BooleanField(default=False, help_text="Repeats every year?")
    
    def __str__(self):
        return f"{self.name} ({self.date})"
    
    class Meta:
        ordering = ['date']

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
    
    class Module(models.TextChoices):
        PAYROLL = 'PAYROLL', 'Payroll'
        ATTENDANCE = 'ATTENDANCE', 'Attendance'
        LEAVES = 'LEAVES', 'Leaves'
        EMPLOYEES = 'EMPLOYEES', 'Employees'
        USERS = 'USERS', 'Users'
        DOCUMENTS = 'DOCUMENTS', 'Documents'
        TICKETS = 'TICKETS', 'Air Tickets'
        SYSTEM = 'SYSTEM', 'System'
        OTHER = 'OTHER', 'Other'
    
    # Who did it
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='audit_logs'
    )
    
    # What was done
    action = models.CharField(max_length=20, choices=Action.choices)
    module = models.CharField(max_length=20, choices=Module.choices, default=Module.OTHER)
    
    # What object was affected (Generic Foreign Key)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Details
    object_repr = models.CharField(max_length=200, blank=True, help_text="String representation of the object")
    changes = models.JSONField(null=True, blank=True, help_text="What changed (old_value/new_value)")
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
            models.Index(fields=['module', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.object_repr or 'System'} at {self.timestamp}"
    
    @property
    def description(self):
        """Returns a human-readable description of the activity matching specific user requirements"""
        user_name = self.user.full_name if (self.user and hasattr(self.user, 'full_name') and self.user.full_name) else (self.user.username if self.user else "System")
        
        # fallback subject
        subject = self.object_repr if self.object_repr else user_name

        # 1. HR & Employee Management
        if self.module in [self.Module.EMPLOYEES, self.Module.USERS]:
            if self.action == self.Action.CREATE:
                return f"Employee {self.object_repr} was added by {user_name}."
                
            if self.action == self.Action.UPDATE:
                # Self-update check
                if self.object_repr and user_name and self.object_repr.lower() == user_name.lower():
                    # Filter out purely self-updates if desired, or just make them simpler
                    return f"{user_name} updated their profile."
                
                # Check for Manager assignment
                if self.changes:
                    changes_str = str(self.changes).lower()
                    if 'manager' in changes_str or 'supervisor' in changes_str:
                         # "Project Manager [User] added [Employee] under his supervision"
                         # Note: The log is usually on the Employee object.
                         # If user_name is the manager, and object_repr is the employee:
                         return f"Project Manager {user_name} added {self.object_repr} under supervision."
                
                return f"{self.object_repr}'s profile was updated by {user_name}."

        # 2. Leave Management
        elif self.module == self.Module.LEAVES:
            if self.action == self.Action.CREATE:
                # "New leave request has been requested by [Employee]"
                # object_repr is typically the employee name for leave logs as per log() method
                return f"New leave request has been requested by {self.object_repr}."
            
            if self.action == self.Action.APPROVE:
                # "Leave request has been accepted for [Employee] by [Manager]"
                # user_name is the approver (Manager)
                return f"Leave request has been accepted for {self.object_repr} by {user_name}."
            
            if self.action == self.Action.REJECT:
                # "The leave request is rejected by [Manager]"
                return f"The leave request is rejected by {user_name}."

        # 3. Attendance
        elif self.module == self.Module.ATTENDANCE:
            if self.action == self.Action.IMPORT:
                return f"Biometric attendance logs were imported by {user_name}."
            # keep detailed log for lateness if needed, or simplify as requested "remove other infos"?
            # User said "remove other infos". I'll keep it simple.
            return f"Attendance record for {self.object_repr} was updated."

        # 4. Payroll
        elif self.module == self.Module.PAYROLL:
            if self.action == self.Action.CREATE:
                # "Payroll was generated by [User]"
                return f"Payroll was generated by {user_name}."
            if self.action == self.Action.EXPORT:
                return f"Payroll bank file was exported by {user_name}."

        # 5. Documents
        elif self.module == self.Module.DOCUMENTS:
            if self.action == self.Action.CREATE:
                # "Document was added by [Employee]"
                # Typically the user uploading is the employee or HR. 
                # If HR uploads for emp, user_name=HR. 
                # The user text "document was added by documents has adde by the employee named" implies they want the uploader name.
                return f"Document was added by {user_name}." 

        # 6. System (Holidays)
        elif self.module == self.Module.SYSTEM:
            is_holiday = 'holiday' in str(self.object_repr).lower() or 'holiday' in str(self.content_type).lower()
            if is_holiday:
                if self.action == self.Action.CREATE:
                    # "Added new holiday [Name] by [User]"
                    return f"Added new holiday {self.object_repr} by {user_name}."
                if self.action in [self.Action.UPDATE, self.Action.DELETE]:
                    # "Upcoming holidays is updated by [User]"
                    return f"Upcoming holidays is updated by {user_name}."
            
        # Default Log
        # If none of the specific cases matched, we try to return a generic string.
        # But user said "remove other infos". 
        # If we return None/Empty here, we need to handle it in template.
        # However, it's safer to return a generic string than nothing to avoid breaking UI layout.
        return f"{user_name} performed {self.action.lower()} on {self.object_repr or 'system'}."
    
    @classmethod
    def log(cls, user, action, obj=None, changes=None, request=None, module=None, object_repr=None):
        """Helper method to create audit logs"""
        
        # Auto-detect module from object type
        if not module and obj:
            model_name = obj.__class__.__name__.lower()
            if 'payroll' in model_name or 'salary' in model_name:
                module = cls.Module.PAYROLL
            elif 'attendance' in model_name:
                module = cls.Module.ATTENDANCE
            elif 'leave' in model_name:
                module = cls.Module.LEAVES
            elif 'employee' in model_name or 'user' in model_name:
                module = cls.Module.EMPLOYEES
            elif 'document' in model_name:
                module = cls.Module.DOCUMENTS
            elif 'ticket' in model_name:
                module = cls.Module.TICKETS
            elif 'holiday' in model_name:
                module = cls.Module.SYSTEM
            else:
                module = cls.Module.OTHER
        
        # Determine object_repr if not provided
        if not object_repr:
            if obj:
                model_name = obj.__class__.__name__.lower()
                if 'attendance' in model_name and hasattr(obj, 'employee'):
                    object_repr = f"Attendance for {obj.employee.full_name or obj.employee.username} on {obj.date}"
                elif 'leaverequest' in model_name and hasattr(obj, 'employee'):
                    # Use only name for leave requests as the type is in the description
                    object_repr = obj.employee.full_name or obj.employee.username
                elif hasattr(obj, 'full_name') and obj.full_name:
                    object_repr = obj.full_name
                elif hasattr(obj, 'username'):
                    object_repr = obj.username
                elif hasattr(obj, 'name'):
                    object_repr = obj.name
                else:
                    object_repr = str(obj)
            elif request:
                # Fallback to request path if no object
                object_repr = "" # description will use user_name
            
            # Enrich changes for CREATE actions of specific models
            if action == cls.Action.CREATE:
                if not changes:
                    changes = {}
                
                model_name = obj.__class__.__name__.lower()
                if 'leaverequest' in model_name:
                    changes['leave_type'] = str(obj.leave_type.name)
                    changes['start_date'] = str(obj.start_date)
                    changes['end_date'] = str(obj.end_date)
                elif 'documentvault' in model_name:
                    changes['document_type'] = str(obj.document_type)
        
        log_entry = cls(
            user=user,
            action=action,
            module=module or cls.Module.OTHER,
            object_repr=object_repr[:200],
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

