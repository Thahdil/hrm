# Nexteons HRMS - Comprehensive Audit Logging System

## Overview
This document describes the complete audit logging implementation for Nexteons HRMS, which automatically tracks all user actions with detailed change history.

## Features Implemented

### 1. Custom AuditLog Model (`core/models.py`)
- **Fields:**
  - `user`: Who performed the action
  - `action`: Type of action (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, APPROVE, REJECT, EXPORT, IMPORT, VIEW)
  - `module`: Which part of the system (PAYROLL, ATTENDANCE, LEAVES, EMPLOYEES, USERS, DOCUMENTS, TICKETS, SYSTEM, OTHER)
  - `object_repr`: String representation of the affected object
  - `changes`: JSON field storing old_value/new_value for each changed field
  - `ip_address`: IP address of the user
  - `user_agent`: Browser/client information
  - `timestamp`: When the action occurred
  - `content_type` & `object_id`: Generic foreign key to the affected object

### 2. Automatic Logging via Middleware (`core/middleware.py`)
- **AuditLogMiddleware**: Captures all POST, PUT, PATCH, DELETE requests
- Automatically detects the module from URL path
- Logs form data changes
- Excludes admin interface, static files, and media files

### 3. Model-Level Change Tracking (`core/signals.py`)
- **Django Signals**: Automatically track model saves and deletes
- **pre_save**: Stores old instance for comparison
- **post_save**: Logs CREATE or UPDATE with field-by-field changes
- **post_delete**: Logs deletion
- **CurrentRequestMiddleware**: Makes request available to signal handlers

### 4. Login/Logout Tracking (`core/auth_views.py`)
- **CustomLoginView**: Logs successful logins
- **CustomLogoutView**: Logs user logouts
- Both include IP address and timestamp

### 5. Enhanced Audit Trail UI (`templates/system_logs.html`)
- Filter by Module and Action
- Expandable change details showing old→new values
- Color-coded actions
- IP address tracking
- Responsive table design

## How It Works

### Automatic Logging
When a user performs any action in the system:

1. **Request Level** (Middleware):
   - Middleware intercepts POST/PUT/PATCH/DELETE requests
   - Extracts form data and URL information
   - Creates audit log entry

2. **Model Level** (Signals):
   - Before save: Stores current state of object
   - After save: Compares old vs new, logs changes
   - After delete: Logs deletion

3. **Authentication** (Custom Views):
   - Login: Logs successful authentication
   - Logout: Logs session termination

### Change Tracking Example

When updating an employee's salary:

```python
# Old value: 5000
# New value: 6000

# Audit log entry created:
{
    "user": "admin",
    "action": "UPDATE",
    "module": "PAYROLL",
    "object": "Employee: John Doe",
    "changes": {
        "basic_salary": {
            "old": "5000.00",
            "new": "6000.00"
        }
    },
    "ip_address": "192.168.1.100",
    "timestamp": "2026-02-03 12:45:00"
}
```

## Usage

### Viewing Audit Logs
1. Navigate to **System Admin > Audit Trail & Logs**
2. Use filters to find specific actions:
   - Filter by Module (Payroll, Attendance, Leaves, etc.)
   - Filter by Action (Create, Update, Delete, etc.)
3. Click "View Changes" to see detailed field-by-field modifications

### Manual Logging (Optional)
You can manually log custom actions in your views:

```python
from core.models import AuditLog

# Log a custom action
AuditLog.log(
    user=request.user,
    action=AuditLog.Action.APPROVE,
    obj=leave_request,
    changes={'status': {'old': 'PENDING', 'new': 'APPROVED'}},
    request=request,
    module=AuditLog.Module.LEAVES
)
```

## Compliance Features

### For Salary Changes
- Old and new values tracked
- User who made the change
- Exact timestamp
- IP address for security

### For Leave Management
- Approval/rejection logged
- Manager who approved
- Changes to dates or duration

### For Attendance
- Import actions logged
- Modifications tracked
- Bulk changes recorded

## Configuration

### Excluded Paths (in `core/middleware.py`)
```python
EXCLUDED_PATHS = [
    '/admin/jsi18n/',
    '/static/',
    '/media/',
    '/__debug__/',
]
```

### Excluded Models (in `core/signals.py`)
```python
EXCLUDED_MODELS = [
    'session',
    'contenttype',
    'permission',
    'logentry',
    'auditlog',  # Don't log audit logs themselves
]
```

## Database Schema

```sql
CREATE TABLE core_auditlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action VARCHAR(20) NOT NULL,
    module VARCHAR(20) NOT NULL DEFAULT 'OTHER',
    object_id INTEGER,
    object_repr VARCHAR(200),
    changes TEXT,  -- JSON
    ip_address VARCHAR(39),
    user_agent TEXT,
    timestamp DATETIME NOT NULL,
    content_type_id INTEGER,
    user_id INTEGER,
    FOREIGN KEY (content_type_id) REFERENCES django_content_type(id),
    FOREIGN KEY (user_id) REFERENCES users_customuser(id)
);

-- Indexes for performance
CREATE INDEX core_auditl_timesta_idx ON core_auditlog (timestamp DESC);
CREATE INDEX core_auditl_user_id_idx ON core_auditlog (user_id, timestamp DESC);
CREATE INDEX core_auditl_action_idx ON core_auditlog (action, timestamp DESC);
CREATE INDEX core_auditl_module_idx ON core_auditlog (module, timestamp DESC);
```

## Middleware Order (Important!)

In `config/settings.py`:
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # Must be before our middleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Custom audit logging middleware
    'core.signals.CurrentRequestMiddleware',  # Stores request in thread-local
    'core.middleware.AuditLogMiddleware',     # Logs HTTP requests
]
```

## Testing the System

1. **Login**: Check if login is logged
2. **Create Employee**: Verify CREATE action is logged
3. **Update Salary**: Confirm old/new values are captured
4. **Approve Leave**: Check APPROVE action with details
5. **Delete Record**: Verify DELETE is logged
6. **Logout**: Confirm logout is tracked

## Troubleshooting

### No logs appearing?
1. Check if middleware is enabled in settings.py
2. Verify signals are registered in core/apps.py
3. Ensure user is authenticated
4. Check excluded paths/models

### Changes not showing?
1. Verify pre_save signal is storing old instance
2. Check if model is in excluded list
3. Ensure JSON serialization is working

### Performance issues?
1. Limit log display to recent 200 entries
2. Add date range filters
3. Archive old logs periodically
4. Use database indexes (already created)

## Security Considerations

- Passwords are never logged (excluded in middleware)
- CSRF tokens excluded from change tracking
- IP addresses logged for security auditing
- Only authenticated users' actions are logged
- Audit logs themselves cannot be modified (no admin interface)

## Future Enhancements

1. **Email Alerts**: Notify admins of critical changes
2. **Export**: Download audit logs as CSV/Excel
3. **Advanced Filters**: Date range, user-specific
4. **Retention Policy**: Auto-archive logs older than X years
5. **Anomaly Detection**: Flag suspicious patterns

## Support

For questions or issues with the audit logging system, contact your system administrator or refer to the Django documentation for signals and middleware.

---

**Last Updated**: February 3, 2026
**Version**: 1.0
**Author**: Nexteons Development Team
