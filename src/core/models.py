from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from datetime import datetime

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
        CANCELLED = 'CANCELLED', 'Cancelled'
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
        MEETINGS = 'MEETINGS', 'Meetings'
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
    
    def format_changes(self):
        if not self.changes:
            return "details updated"
        
        parts = []
        if isinstance(self.changes, dict):
            for k, v in self.changes.items():
                if isinstance(v, list) and len(v) == 2:
                    parts.append(f"{k} changed from '{v[0]}' to '{v[1]}'")
                else:
                    parts.append(f"{k}: {v}")
        return ", ".join(parts)
    
    def _get_change_vals(self, field_name):
        """Helper to extract old/new values and resolve choices to human labels"""
        if not self.changes or not isinstance(self.changes, dict):
            return "Unknown", "Unknown"
        
        val = self.changes.get(field_name)
        if val is None:
            return "Unknown", "Unknown"
        
        # 1. Extract raw values (handle both dict and list formats)
        if isinstance(val, dict):
            old = val.get('old')
            new = val.get('new')
        elif isinstance(val, list) and len(val) == 2:
            old, new = val[0], val[1]
        else:
            old, new = None, str(val)
            
        # 2. Try to resolve codes to labels using model choices
        if self.content_type:
            try:
                model_cls = self.content_type.model_class()
                if model_cls:
                    field = model_cls._meta.get_field(field_name)
                    if field and field.choices:
                        choices_dict = {str(c_val): str(c_label) for c_val, c_label in field.choices}
                        if old is not None: old = choices_dict.get(str(old), old)
                        if new is not None: new = choices_dict.get(str(new), new)
            except:
                pass
        
        # 3. Final formatting for UI
        def format_val(v):
            if v is None or str(v).lower() in ['none', 'nan', 'null', '']:
                return "Not set"
            return str(v)
            
        return format_val(old), format_val(new)

    @property
    def description(self):
        """Returns a human-readable description matching specific user requirements"""
        user_name = self.user.full_name if (self.user and hasattr(self.user, 'full_name') and self.user.full_name) else (self.user.username if self.user else "System")
        
        # --- Live Recovery & Healing Strategy ---
        # If the stored name is generic or missing, try to find the real identity
        obj_name = self.object_repr
        # Define what we consider "junk" or "placeholder" names
        placeholders = ['unknown', 'new record', 'customuser object', 'none', '', 'entry', 'system record']
        
        def is_junk(name):
            return not name or str(name).lower().strip() in placeholders

        if is_junk(obj_name):
            # 1. Try Live Object lookup (if not deleted from DB)
            if self.content_object:
                try:
                    obj_name = str(self.content_object)
                except:
                    pass
            
            # 2. Deep Recovery from JSON changes history
            if is_junk(obj_name) and self.changes:
                # A. Check top-level (Signal logs)
                # B. Check nested 'new_values' (Old Middleware logs)
                targets = [self.changes]
                if 'new_values' in self.changes:
                    targets.append(self.changes['new_values'])
                
                name_keys = ['full_name', 'username', 'employee_id', 'name', 'title']
                for target in targets:
                    for key in name_keys:
                        if key in target:
                            val = target[key]
                            # Handle different value formats: [old, new], {'new': x}, or simple string
                            if isinstance(val, list) and len(val) >= 2:
                                obj_name = val[1]
                            elif isinstance(val, dict):
                                obj_name = val.get('new') or val.get('value')
                            else:
                                obj_name = str(val)
                            
                            if not is_junk(obj_name): break
                    if not is_junk(obj_name): break
        
        # FINAL SANITY: If it's still generic, don't show "Entry", 
        # use the ID if available, else a very generic but honest label
        if is_junk(obj_name):
            if self.object_id:
                obj_name = f"Item #{self.object_id}"
            else:
                obj_name = "Record"
        
        # 1. Employee Management
        if self.module == self.Module.EMPLOYEES:
            if self.action == self.Action.CREATE:
                return f"New employee '{obj_name}' was onboarded by {user_name}."
            
            if self.action == self.Action.UPDATE and self.changes and isinstance(self.changes, dict):
                # Check for specific interesting fields
                if 'department' in self.changes:
                    old, new = self._get_change_vals('department')
                    return f"Department for {obj_name} changed from {old} to {new}."
                
                if 'designation' in self.changes:
                    old, new = self._get_change_vals('designation')
                    return f"Designation for {obj_name} changed from {old} to {new}."
                
                if 'salary_basic' in self.changes:
                    return f"Basic Salary for {obj_name} was updated by {user_name}."
                
                if 'status' in self.changes:
                    old, new = self._get_change_vals('status')
                    if str(new).upper() in ['INACTIVE', 'RESIGNED', 'TERMINATED']:
                        return f"{obj_name} has been marked as '{new}' as of today."
                    return f"Status for {obj_name} changed to '{new}'."
                
                # If we have any other change but it's not one of the above, still try to show something
                # unless we want to hide "technical" changes.
                return None

        if self.module == self.Module.LEAVES:
            if self.action == self.Action.CREATE:
                # changes usually contains leave_type, start_date, end_date for Create
                leave_type = "Leave"
                duration_str = ""
                
                if self.changes and isinstance(self.changes, dict):
                    leave_type = self.changes.get('leave_type', 'Leave')
                    
                    # Try to get duration
                    dur = self.changes.get('duration')
                    
                    # Fallback for old logs: Calculate from start/end
                    if not dur:
                        start = self.changes.get('start_date')
                        end = self.changes.get('end_date')
                        if start and end:
                            try:
                                d1 = datetime.strptime(start, "%Y-%m-%d")
                                d2 = datetime.strptime(end, "%Y-%m-%d")
                                # This calculation assumes 1 day per date difference + 1 (inclusive)
                                # It won't detect half-days for old logs, but is better than nothing.
                                days = (d2 - d1).days + 1
                                dur = days
                            except:
                                pass
                    
                    if dur:
                        try:
                            val = float(dur)
                            if val == 0.5:
                                duration_str = " for a Half Day"
                            elif val == 1:
                                duration_str = " for 1 day"
                            else:
                                # Show decimals only if needed
                                duration_str = f" for {val:g} days"
                        except:
                            duration_str = f" for {dur} days"

                return f"{obj_name} submitted a {leave_type} request{duration_str}."
            
            if self.action == self.Action.APPROVE:
                return f"Leave for {obj_name} was Approved by {user_name}."
            
            if self.action == self.Action.REJECT:
                return f"Leave for {obj_name} was Rejected by {user_name}."

        if self.module == self.Module.ATTENDANCE:
            if self.action == self.Action.CREATE or self.action == self.Action.IMPORT:
                # "Late Arrivals" logic would require parsing changes or status
                # For now, generic attendance log
                if "late" in obj_name.lower():
                     return f"{obj_name} checked in late."
                return f"Attendance recorded for {obj_name}."

        # 3. Payroll & Compliance
        if self.module == self.Module.PAYROLL:
            if self.action == self.Action.CREATE:
                 # object_repr is usually "PayrollBatch for Jan 2026"
                 return f"Payroll for {obj_name.replace('PayrollBatch for ', '')} has been finalized."
            if self.action == self.Action.EXPORT:
                 return f"Payroll for {obj_name.replace('PayrollBatch for ', '')} was exported."

        # 4. System & Security
        if self.action == self.Action.LOGIN:
            ip = self.ip_address if self.ip_address else "Unknown IP"
            return f"{user_name} logged in from IP address: {ip}."
            
        if self.module == self.Module.SYSTEM and self.action == self.Action.UPDATE:
             return f"{user_name} updated System Settings."

        # 5. Meetings Management
        if self.module == self.Module.MEETINGS:
            meeting_title = obj_name
            if self.action == self.Action.CREATE:
                # Get meeting time from changes if available
                scheduled_time = ""
                if self.changes and 'start_time' in self.changes:
                    scheduled_time = f" for {self.changes['start_time']}"
                return f"{user_name} scheduled a new meeting '{meeting_title}'{scheduled_time}."
            
            if self.action == self.Action.UPDATE:
                return f"{user_name} updated the meeting '{meeting_title}'."
            
            if self.action == self.Action.DELETE or self.action == self.Action.CANCELLED:
                return f"{user_name} cancelled the meeting '{meeting_title}'."

        # Return None for everything else to filter it out
        return None
    
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
            elif 'meeting' in model_name:
                module = cls.Module.MEETINGS
            else:
                module = cls.Module.OTHER
        
        # Determine object_repr if not provided
        if not object_repr:
            if obj:
                # 1. Try common identity fields
                for attr in ['full_name', 'username', 'name', 'title', 'label']:
                    val = getattr(obj, attr, None)
                    if val:
                        object_repr = str(val)
                        break
                
                # 2. Special handling for User model if fields were empty
                if not object_repr and hasattr(obj, 'get_full_name'):
                    f_name = obj.get_full_name()
                    if f_name: object_repr = f_name
                
                # 3. Fallback to string representation
                if not object_repr:
                    object_repr = str(obj)
                
                # 4. Final safety fallback
                if not object_repr or str(object_repr).strip().lower() in ['', 'none', 'unknown']:
                    object_repr = f"{obj.__class__.__name__} #{obj.pk}"
            
            elif request:
                # Use request path as a last resort
                object_repr = f"{request.method} {request.path}"
            else:
                object_repr = "Unknown"
            
        # Enrich changes for CREATE actions to capture identity for future recovery
        if action == cls.Action.CREATE and obj:
            if not changes: changes = {}
            for attr in ['full_name', 'username', 'name', 'title']:
                val = getattr(obj, attr, None)
                if val: changes[attr] = str(val)
        
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

