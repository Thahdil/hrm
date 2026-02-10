from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.http import HttpResponse
from django.utils import timezone
from django import forms
from .models import PayrollBatch, PayrollEntry, AttendanceLog, DeductionComponent, EmployeeDeduction, PayrollDeduction
from .services import BankTransferService, PayrollService

class CsvImportForm(forms.Form):
    csv_file = forms.FileField()

@admin.register(PayrollBatch)
class PayrollBatchAdmin(admin.ModelAdmin):
    list_display = ('month', 'generated_at', 'download_sif_link')
    change_list_template = "admin/payroll_changelist.html"

    def download_sif_link(self, obj):
        if obj.sif_file:
            return f"<a href='{obj.sif_file.url}'>Download Export</a>"
        return "No File"
    download_sif_link.allow_tags = True
    download_sif_link.short_description = "Bank File"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('generate-payroll/', self.admin_site.admin_view(self.generate_payroll_view), name='payroll_generate'),
        ]
        return my_urls + urls

    def generate_payroll_view(self, request):
        if request.method == "POST":
            # 1. Create Batch for current month (Start of month)
            today = timezone.now().date()
            batch_date = today.replace(day=1)
            
            batch = PayrollBatch.objects.create(month=batch_date)
            
            # 2. Calculate Entries
            PayrollService.calculate_payroll(batch)
            
            # 3. Generate Export
            file_content = BankTransferService.generate_export_file(batch)
            
            # 4. Save file
            from django.core.files.base import ContentFile
            batch.sif_file.save(f"BankTransfer_{batch_date.strftime('%Y%m')}.csv", ContentFile(file_content))
            batch.save()
            
            self.message_user(request, "Payroll Generated and Bank Export created successfully.")
            return redirect("admin:payroll_payrollbatch_changelist")
            
        return redirect("admin:payroll_payrollbatch_changelist")

@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'check_in', 'check_out', 'status', 'total_work_minutes', 'approved_overtime_minutes', 'is_locked')
    list_filter = ('entry_type', 'status', 'is_locked', 'is_compliant')
    search_fields = ('employee__username', 'employee__full_name', 'employee__email')
    change_list_template = "admin/attendance_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('import-attendance/', self.admin_site.admin_view(self.import_attendance_view), name='attendance_import'),
        ]
        return my_urls + urls

    def import_attendance_view(self, request):
        if request.method == "POST":
            form = CsvImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                # Pass to service
                PayrollService.import_attendance_csv(csv_file, timezone.now().date())
                self.message_user(request, "Attendance Imported Successfully")
                return redirect("admin:payroll_attendancelog_changelist")
        
        form = CsvImportForm()
        payload = {"form": form}
        return render(request, "admin/csv_form.html", payload)

@admin.register(DeductionComponent)
class DeductionComponentAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_statutory', 'is_recurring')

@admin.register(EmployeeDeduction)
class EmployeeDeductionAdmin(admin.ModelAdmin):
    list_display = ('employee', 'component', 'amount', 'percentage', 'is_active')
    list_filter = ('is_active', 'component')
    search_fields = ('employee__username', 'employee__full_name')

@admin.register(PayrollDeduction)
class PayrollDeductionAdmin(admin.ModelAdmin):
    list_display = ('payroll_entry', 'component', 'amount', 'approved_amount', 'is_waived')
    list_filter = ('is_waived', 'component')

