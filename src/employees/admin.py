from django.contrib import admin
from .models import DocumentVault

@admin.register(DocumentVault)
class DocumentVaultAdmin(admin.ModelAdmin):
    list_display = ('employee', 'document_type', 'expiry_date', 'status', 'is_expiring_soon_badge')
    list_filter = ('document_type', 'status')
    
    @admin.display(description='Expiring Soon', boolean=True)
    def is_expiring_soon_badge(self, obj):
        return obj.is_expiring_soon()
