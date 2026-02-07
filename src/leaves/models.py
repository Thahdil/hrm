from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class LeaveType(models.Model):
    name = models.CharField(max_length=50) # Annual, Sick, Unpaid, Maternity
    code = models.CharField(max_length=10, unique=True) # ANN, SCK, UNP
    days_entitlement = models.IntegerField(default=30, help_text="Annual entitlement days")
    is_paid = models.BooleanField(default=True)
    is_carry_forward = models.BooleanField(default=False)
    encashable = models.BooleanField(default=False, help_text="Can be encashed at EOS")
    
    # New Duration Logic
    duration_days = models.IntegerField(null=True, blank=True, help_text="Fixed duration in days. Set to 1 for 'Normal Day', 30 for 'Annual', or Leave Empty for Manual.")

    ACCRUAL_CHOICES = [
        ('ANNUAL', 'Annual (Upfront)'),
        ('MONTHLY', 'Monthly (Pro-rata)'),
    ]
    accrual_frequency = models.CharField(
        max_length=20,
        choices=ACCRUAL_CHOICES,
        default='ANNUAL'
    )

    # Eligibility Criteria
    class GenderLimit(models.TextChoices):
        ALL = "ALL", "All Employees"
        MALE = "Male", "Male Only"
        FEMALE = "Female", "Female Only"

    eligibility_gender = models.CharField(max_length=10, choices=GenderLimit.choices, default=GenderLimit.ALL, help_text="Who is eligible for this leave?")
    min_service_days = models.IntegerField(default=0, help_text="Minimum days of service required to apply")

    def get_monthly_accrual(self):
        if self.accrual_frequency == 'MONTHLY':
            return self.days_entitlement / 12
        return 0

    # Audit
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class LeaveBalance(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    year = models.IntegerField(default=2024)
    
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    total_entitlement = models.FloatField(default=30.0)
    days_used = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def remaining(self):
        return self.total_entitlement - self.days_used

    class Meta:
        unique_together = ('employee', 'leave_type', 'year')
        
    def __str__(self):
        return f"{self.employee.full_name} - {self.leave_type.code}: {self.remaining}"

class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Manager"
        MGR_APPROVED = "MGR_APPROVED", "Manager Approved"
        HR_PROCESSED = "HR_PROCESSED", "HR Processed"
        APPROVED = "APPROVED", "Completed"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_requests')
    assigned_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_leave_requests',
        limit_choices_to={'role__in': ['PROJECT_MANAGER', 'CEO']}
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    reason = models.TextField(blank=True)
    
    # Workflow
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Audit
    manager_comment = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    rejection_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def clean(self):
        # Auto-calculate end_date based on duration_days if set
        # But SKIP for Annual/Maternity as they are now "Manual with Cap"
        is_manual_cap = False
        if self.leave_type_id and self.leave_type.name:
            n = self.leave_type.name.lower()
            if 'annual' in n or 'maternity' in n:
                is_manual_cap = True

        if not is_manual_cap and self.leave_type_id and hasattr(self.leave_type, 'duration_days') and self.leave_type.duration_days:
            # If duration is 1 (Normal Day), End = Start
            if self.leave_type.duration_days == 1:
                self.end_date = self.start_date
                
            # If duration > 1 (e.g. Some fixed package), End = Start + (Duration - 1)
            elif self.leave_type.duration_days > 1:
                self.end_date = self.start_date + timedelta(days=self.leave_type.duration_days - 1)
                
        # Call parent clean
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def duration_days(self):
        if not self.end_date or not self.start_date:
            return 0
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.employee.full_name} - {self.leave_type.code} ({self.start_date})"

class TicketRequest(models.Model):
    class TicketStatus(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        MGR_APPROVED = "MGR_APPROVED", "Manager Approved"
        HR_PROCESSED = "HR_PROCESSED", "HR Processed"
        BOOKED = "BOOKED", "Booked"
        ENCASHED = "ENCASHED", "Encashed"
        REJECTED = "REJECTED", "Rejected"

    class BenefitType(models.TextChoices):
        TICKET = "TICKET", "Flight Ticket"
        CASH = "CASH", "Cash Encashment"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ticket_requests')
    destination = models.CharField(max_length=100, help_text="Home Country Airport")
    travel_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    
    benefit_type = models.CharField(max_length=10, choices=BenefitType.choices, default=BenefitType.TICKET)
    is_encashment = models.BooleanField(default=False, help_text="Deprecated: Use benefit_type")
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost or Cash value")
    
    status = models.CharField(max_length=20, choices=TicketStatus.choices, default=TicketStatus.REQUESTED)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ticket for {self.employee.full_name} to {self.destination}"
