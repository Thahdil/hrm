from django.db import models
from django.conf import settings

class DocumentVault(models.Model):
    class DocumentType(models.TextChoices):
        AADHAAR = "AADHAAR", "Aadhaar Card"
        PAN = "PAN", "PAN Card"
        PASSPORT = "PASSPORT", "Passport"
        DEGREE = "DEGREE", "Degree Certificate"
        BANK_PROOF = "BANK_PROOF", "Bank Passbook"

    class DocStatus(models.TextChoices):
        VALID = "VALID", "Valid"
        EXPIRED = "EXPIRED", "Expired"
        RENEWAL = "RENEWAL", "Renewal in Progress"
        ARCHIVED = "ARCHIVED", "Archived"

    # Encrypted fields logic for specific documents can be handled here or in Employee
    # The prompt asks for secure storage of digital copies (files) here.

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=10, choices=DocumentType.choices)
    status = models.CharField(max_length=20, choices=DocStatus.choices, default=DocStatus.VALID)
    
    # Secure File Upload
    file = models.FileField(upload_to='secure_docs/%Y/%m/')
    
    # Metadata
    expiry_date = models.DateField(null=True, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notification_sent_at = models.DateTimeField(null=True, blank=True, help_text="When the last expiry alert was triggered")

    @property
    def is_expired(self):
        from datetime import date
        if not self.expiry_date:
            return False
        return self.expiry_date < date.today()

    def is_expiring_soon(self, days=30):
        # Expiry Alert Logic: Currently valid but expires within 'days'
        from datetime import date, timedelta
        if not self.expiry_date:
            return False
        return date.today() <= self.expiry_date <= (date.today() + timedelta(days=days))

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.employee.full_name}"
