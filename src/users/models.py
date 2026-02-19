from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from core.utils.encryption import EncryptionUtils
from .models_otp import OTPToken

class CustomUser(AbstractUser):
    # Role System
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        HR_MANAGER = "HR_MANAGER", "HR Manager"
        CEO = "CEO", "CEO"
        PROJECT_MANAGER = "PROJECT_MANAGER", "Project Manager"
        EMPLOYEE = "EMPLOYEE", "Employee"

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.EMPLOYEE)
    additional_role = models.CharField(max_length=50, choices=Role.choices, blank=True, null=True, help_text="Optional secondary role")

    # Status System
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')
        SUSPENDED = 'SUSPENDED', _('Suspended')
        ARCHIVED = 'ARCHIVED', _('Archived')
        PENDING = 'PENDING', _('Pending')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Employee Fields Merged Here ---
    
    # Basic Info (email, first_name, last_name are in AbstractUser)
    # user.get_full_name() exists, but we can add full_name field or use property
    # Employee had 'full_name' field. AbstractUser has first_name, last_name.
    # I'll keep 'full_name' for compatibility with existing code or map it.
    # Existing code uses emp.full_name. I'll add the field to be safe.
    full_name = models.CharField(max_length=255, blank=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="Company-assigned Employee Code")
    phone_number = models.CharField(max_length=20, blank=True)

    # Employment Details
    class Department(models.TextChoices):
        HR = "HR", "Human Resources"
        IT = "IT", "Information Technology"
        SALES = "SALES", "Sales & Marketing"
        FINANCE = "FINANCE", "Finance"
        OPS = "OPERATIONS", "Operations"
        ADMIN = "ADMIN", "Administration"

    department = models.CharField(max_length=100, choices=Department.choices, default=Department.IT)
    date_of_joining = models.DateField(null=True, blank=True)
    
    class Designation(models.TextChoices):
        # IT
        FRONTEND_DEV    = "FRONTEND",        "Frontend Developer"
        BACKEND_DEV     = "BACKEND",         "Backend Developer"
        DESIGNER        = "DESIGNER",        "Designer"
        PROJECT_MANAGER = "PROJECT_MANAGER", "Project Manager"
        QC              = "QC",              "QC (Quality Control)"
        # HR
        HR_EXECUTIVE    = "HR_EXECUTIVE",    "HR Executive"
        HR_MANAGER      = "HR_MANAGER",      "HR Manager"
        RECRUITER       = "RECRUITER",       "Recruiter"
        PAYROLL_SPEC    = "PAYROLL_SPEC",    "Payroll Specialist"
        # Sales & Marketing
        SALES_EXEC      = "SALES_EXEC",      "Sales Executive"
        SALES_MANAGER   = "SALES_MANAGER",   "Sales Manager"
        MARKETING_EXEC  = "MARKETING_EXEC",  "Marketing Executive"
        BIZ_DEV         = "BIZ_DEV",         "Business Development"
        # Finance
        ACCOUNTANT      = "ACCOUNTANT",      "Accountant"
        FINANCE_MANAGER = "FINANCE_MANAGER", "Finance Manager"
        AUDITOR         = "AUDITOR",         "Auditor"
        # Operations
        OPS_EXECUTIVE   = "OPS_EXECUTIVE",   "Operations Executive"
        OPS_MANAGER     = "OPS_MANAGER",     "Operations Manager"
        LOGISTICS_COORD = "LOGISTICS_COORD", "Logistics Coordinator"
        # Administration
        ADMIN_EXECUTIVE = "ADMIN_EXECUTIVE", "Admin Executive"
        OFFICE_MANAGER  = "OFFICE_MANAGER",  "Office Manager"
        RECEPTIONIST    = "RECEPTIONIST",    "Receptionist"

    designation = models.CharField(max_length=100, choices=Designation.choices, blank=True, null=True, default=None)
    salary_basic = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Basic Salary in INR")
    salary_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total Allowances in INR")

    class ContractType(models.TextChoices):
        LIMITED = 'LIMITED', 'Limited Contract'
        UNLIMITED = 'UNLIMITED', 'Unlimited Contract'
    
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.LIMITED)
    
    # Personal & Compliance
    aadhaar_number = models.CharField(max_length=12, blank=True, null=True, help_text="Aadhaar Card Number (12 Digits)", validators=[RegexValidator(r'^\d{12}$', 'Must be exactly 12 digits')])
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    
    class Gender(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"
        OTHER = "Other", "Other"
    
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True, null=True)

    # Encrypted Fields (Backing fields)
    _pan_number = models.CharField(max_length=255, db_column="pan_number", help_text="Encrypted PAN Card Number", blank=True, null=True)
    _passport_number = models.CharField(max_length=255, db_column="passport_number", help_text="Encrypted Passport Number", blank=True, null=True)
    _iban = models.CharField(max_length=255, db_column="iban", help_text="Encrypted Account Number / IBAN", blank=True, null=True)
    
    # New Field for Indian Banking
    ifsc_code = models.CharField(max_length=11, blank=True, null=True, help_text="Bank IFSC Code (11 Characters)", validators=[RegexValidator(r'^[A-Z]{4}0[A-Z0-9]{6}$', 'Invalid IFSC format (e.g., HDFC0001234)')])

    # Hierarchy
    managers = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='subordinates', help_text="Managers assigned to this employee")

    def save(self, *args, **kwargs):
        # Auto-pad Aadhaar ID to 12 digits if present
        if self.aadhaar_number:
            self.aadhaar_number = str(self.aadhaar_number).strip().zfill(12)
        
        # Ensure full_name is uppercase
        if self.full_name:
            self.full_name = self.full_name.upper()
            
        super().save(*args, **kwargs)

    # Methods
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.additional_role == self.Role.ADMIN
    
    def is_hr(self):
        return self.role == self.Role.HR_MANAGER or self.additional_role == self.Role.HR_MANAGER

    def is_ceo(self):
        return self.role == self.Role.CEO or self.additional_role == self.Role.CEO

    def is_project_manager(self):
        return self.role == self.Role.PROJECT_MANAGER or self.additional_role == self.Role.PROJECT_MANAGER
        
    def is_employee(self):
        return self.role == self.Role.EMPLOYEE # Employee is default/base, typically no additional_role check needed unless we want inclusive checking

    def __str__(self):
        if self.full_name: return self.full_name
        if self.username: return self.username
        if self.employee_id: return f"Employee {self.employee_id}"
        return f"User #{self.pk}" if self.pk else "New User"

    @property
    def total_salary(self):
        return self.salary_basic + self.salary_allowance

    # --- Encryption Accessors ---
    @property
    def pan_number(self):
        return EncryptionUtils.decrypt(self._pan_number) if self._pan_number else None
    
    @pan_number.setter
    def pan_number(self, value):
        self._pan_number = EncryptionUtils.encrypt(value) if value else None

    @property
    def passport_number(self):
        return EncryptionUtils.decrypt(self._passport_number) if self._passport_number else None
    
    @passport_number.setter
    def passport_number(self, value):
        self._passport_number = EncryptionUtils.encrypt(value) if value else None

    @property
    def iban(self):
        return EncryptionUtils.decrypt(self._iban) if self._iban else None

    @iban.setter
    def iban(self, value):
        self._iban = EncryptionUtils.encrypt(value) if value else None