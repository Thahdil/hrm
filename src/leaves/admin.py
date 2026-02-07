from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import LeaveType, LeaveRequest, LeaveBalance, TicketRequest

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'days_entitlement', 'is_paid')

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'year', 'total_entitlement', 'days_used', 'remaining')
    search_fields = ('employee__full_name',)
    list_filter = ('year', 'leave_type')

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'status', 'duration_days')
    list_filter = ('status', 'leave_type')
    search_fields = ('employee__full_name',)
    actions = ['approve_leave', 'reject_leave']

    @admin.action(description='Approve selected Leave Requests')
    def approve_leave(self, request, queryset):
        # In a real app, this would also deduct from balance
        rows_updated = queryset.update(status=LeaveRequest.Status.APPROVED, approved_by=request.user)
        
        # Logic to deduct balance could go here (iterating over queryset)
        for req in queryset:
            if req.status == LeaveRequest.Status.APPROVED:
                # Update Balance
                try:
                    balance, created = LeaveBalance.objects.get_or_create(
                        employee=req.employee,
                        leave_type=req.leave_type,
                        year=req.start_date.year,
                        defaults={'total_entitlement': req.leave_type.days_entitlement}
                    )
                    balance.days_used += req.duration_days
                    balance.save()
                except Exception:
                    pass # Handle specific errors

        self.message_user(request, f"{rows_updated} leave requests approved.")

    @admin.action(description='Reject selected Leave Requests')
    def reject_leave(self, request, queryset):
        rows_updated = queryset.update(status=LeaveRequest.Status.REJECTED)
        self.message_user(request, f"{rows_updated} leave requests rejected.")

@admin.register(TicketRequest)
class TicketRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'destination', 'travel_date', 'is_encashment', 'status', 'amount')
    list_filter = ('status', 'is_encashment')
