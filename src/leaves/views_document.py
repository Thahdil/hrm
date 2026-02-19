from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect

@login_required
def leave_upload_document(request, pk):
    from django.shortcuts import get_object_or_404
    from .models import LeaveRequest
    
    leave = get_object_or_404(LeaveRequest, pk=pk)
    
    # Permission Check: Only the employee can upload
    if leave.employee != request.user:
        messages.error(request, "You do not have permission to upload documents for this leave.")
        return redirect('leave_detail', pk=pk)
        
    # State Check: Must be Approved and waiting for document
    if leave.status != 'APPROVED' or leave.document_status not in ['PENDING', 'REJECTED']:
         messages.error(request, "Document upload is not required or allowed at this stage.")
         return redirect('leave_detail', pk=pk)
         
    if request.method == 'POST' and request.FILES.get('attachment'):
        leave.attachment = request.FILES['attachment']
        leave.document_status = LeaveRequest.DocumentStatus.UPLOADED
        leave.save()
        messages.success(request, "Medical certificate uploaded successfully. Waiting for HR verification.")
        
        # Log
        from core.models import AuditLog
        AuditLog.log(
            user=request.user, 
            action=AuditLog.Action.UPDATE, 
            obj=leave, 
            request=request, 
            module=AuditLog.Module.LEAVES, 
            object_repr="Medical Certificate Upload"
        )
        
    return redirect('leave_detail', pk=pk)

@login_required
def leave_verify_document(request, pk):
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from .models import LeaveRequest
    
    leave = get_object_or_404(LeaveRequest, pk=pk)
    user = request.user
    
    # Permission Check: HR, Admin, CEO, or Assigned Manager
    is_authorized = (
        user.is_hr() or 
        user.is_admin() or 
        user.is_ceo() or 
        (leave.assigned_manager == user)
    )
    
    if not is_authorized:
        messages.error(request, "You do not have permission to verify documents.")
        return redirect('leave_detail', pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'verify':
            leave.document_status = LeaveRequest.DocumentStatus.VERIFIED
            leave.payment_status = LeaveRequest.PaymentStatus.PAID
            leave.verified_by = user
            leave.verification_date = timezone.now()
            leave.save()
            messages.success(request, "Document verified. Leave marked as PAID.")
            
        elif action == 'reject':
            leave.document_status = LeaveRequest.DocumentStatus.REJECTED
            leave.payment_status = LeaveRequest.PaymentStatus.LOP
            leave.verified_by = user
            leave.verification_date = timezone.now()
            leave.rejection_reason = request.POST.get('rejection_reason', '')
            leave.save()
            messages.warning(request, "Document rejected. Leave marked as LOSS OF PAY.")
            
    return redirect('leave_detail', pk=pk)
