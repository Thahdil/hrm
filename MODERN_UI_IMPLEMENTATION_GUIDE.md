# Nexteons HRMS - Modern UI Implementation Guide

## Overview
This guide explains how to apply the new modern design system across your entire HRMS application. The design is inspired by contemporary dashboard UIs with Nexteons branding (orange primary color).

## What's Been Created

### 1. Design System (`static/css/modern.css`)
- **Color Palette**: Orange primary (#FF6B35) matching Nexteons brand
- **Typography**: Inter font family for clean, modern look
- **Components**: Cards, buttons, forms, tables, badges
- **Layout**: Sidebar + main content area
- **Responsive**: Mobile-friendly design

### 2. Base Template (`templates/base_modern.html`)
- Modern sidebar navigation
- Top bar with search and notifications
- User profile menu
- Organized navigation sections
- Nexteons logo integration

### 3. Dashboard (`templates/dashboard_modern.html`)
- Stats cards with gradients and icons
- Recent activity feed
- Quick actions panel
- Pending approvals table
- Upcoming events

## How to Apply to Your Entire App

### Step 1: Update All Templates

Replace the first line of each template from:
```django
{% extends 'base.html' %}
```

To:
```django
{% extends 'base_modern.html' %}
```

### Step 2: Update Content Blocks

The new base template uses these blocks:
- `{% block title %}` - Page title
- `{% block header_title %}` - Main heading in top bar
- `{% block page_subtitle %}` - Subtitle under heading
- `{% block content %}` - Main page content

### Step 3: Use Modern Components

#### Stats Cards
```html
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-header">
            <div class="stat-icon" style="background: var(--primary-gradient); color: white;">
                <i class="ri-team-line"></i>
            </div>
            <div class="stat-change positive">
                <i class="ri-arrow-up-line"></i>
                +12%
            </div>
        </div>
        <div class="stat-value">150</div>
        <div class="stat-label">Total Employees</div>
    </div>
</div>
```

#### Cards
```html
<div class="card">
    <div class="card-header">
        <div>
            <h3 class="card-title">Card Title</h3>
            <p class="card-subtitle">Card subtitle</p>
        </div>
        <button class="btn btn-primary">Action</button>
    </div>
    <!-- Card content -->
</div>
```

#### Buttons
```html
<button class="btn btn-primary">Primary Button</button>
<button class="btn btn-secondary">Secondary Button</button>
<button class="btn btn-outline">Outline Button</button>
```

#### Tables
```html
<div class="table-container">
    <table>
        <thead>
            <tr>
                <th>Column 1</th>
                <th>Column 2</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Data 1</td>
                <td>Data 2</td>
            </tr>
        </tbody>
    </table>
</div>
```

#### Badges
```html
<span class="badge badge-success">Approved</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-error">Rejected</span>
<span class="badge badge-info">Info</span>
```

#### Forms
```html
<div class="form-group">
    <label class="form-label">Field Label</label>
    <input type="text" class="form-input" placeholder="Enter value">
</div>

<div class="form-group">
    <label class="form-label">Select Field</label>
    <select class="form-select">
        <option>Option 1</option>
        <option>Option 2</option>
    </select>
</div>
```

## Quick Migration Checklist

### Templates to Update:
- [ ] `dashboard.html` → Use `dashboard_modern.html` as reference
- [ ] `employees/employee_list.html`
- [ ] `employees/employee_detail.html`
- [ ] `employees/employee_form.html`
- [ ] `leaves/leave_list.html`
- [ ] `leaves/leave_form.html`
- [ ] `payroll/payroll_list.html`
- [ ] `payroll/attendance_list.html`
- [ ] `system_logs.html`
- [ ] All other templates

### For Each Template:

1. **Change extends**:
   ```django
   {% extends 'base_modern.html' %}
   ```

2. **Update blocks**:
   ```django
   {% block title %}Page Title - Nexteons HRMS{% endblock %}
   {% block header_title %}Page Title{% endblock %}
   {% block page_subtitle %}Brief description{% endblock %}
   ```

3. **Wrap content in cards**:
   ```django
   {% block content %}
   <div class="card">
       <!-- Your existing content -->
   </div>
   {% endblock %}
   ```

4. **Update buttons**:
   - Replace old button classes with `btn btn-primary`, `btn btn-secondary`, etc.

5. **Update tables**:
   - Wrap tables in `<div class="table-container">`

6. **Update forms**:
   - Use `form-group`, `form-label`, `form-input` classes

## Color Scheme

### Primary (Nexteons Orange)
- `var(--primary)` - #FF6B35
- `var(--primary-light)` - #FF8C61
- `var(--primary-dark)` - #E55A2B
- `var(--primary-gradient)` - Orange gradient

### Semantic Colors
- `var(--success)` - #10B981 (Green)
- `var(--warning)` - #F59E0B (Yellow)
- `var(--error)` - #EF4444 (Red)
- `var(--info)` - #3B82F6 (Blue)

### Neutrals
- `var(--gray-50)` to `var(--gray-900)` - Gray scale
- `var(--white)` - #FFFFFF

## Icons

Using Remix Icon library:
- Dashboard: `ri-dashboard-3-line`
- Employees: `ri-team-line`
- Calendar: `ri-calendar-check-line`
- Money: `ri-money-dollar-circle-line`
- Documents: `ri-folder-shield-line`
- Settings: `ri-settings-3-line`
- User: `ri-user-line`
- Add: `ri-add-line`
- Edit: `ri-edit-line`
- Delete: `ri-delete-bin-line`

Full icon list: https://remixicon.com/

## Example: Converting Employee List

### Before (old template):
```django
{% extends 'base.html' %}
{% block content %}
<h2>Employees</h2>
<table>
    <tr>
        <th>Name</th>
        <th>Email</th>
    </tr>
    {% for emp in employees %}
    <tr>
        <td>{{ emp.name }}</td>
        <td>{{ emp.email }}</td>
    </tr>
    {% endfor %}
</table>
{% endblock %}
```

### After (modern template):
```django
{% extends 'base_modern.html' %}

{% block title %}Employees - Nexteons HRMS{% endblock %}
{% block header_title %}Employees{% endblock %}
{% block page_subtitle %}Manage your team members{% endblock %}

{% block content %}
<div class="card">
    <div class="card-header">
        <div>
            <h3 class="card-title">All Employees</h3>
            <p class="card-subtitle">{{ employees.count }} total employees</p>
        </div>
        <a href="{% url 'employee_create' %}" class="btn btn-primary">
            <i class="ri-add-line"></i>
            Add Employee
        </a>
    </div>
    
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for emp in employees %}
                <tr>
                    <td>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <div class="user-avatar">{{ emp.user.username|slice:":1"|upper }}</div>
                            <div>
                                <div style="font-weight: 600;">{{ emp.user.full_name }}</div>
                                <div style="font-size: 12px; color: var(--gray-500);">{{ emp.designation }}</div>
                            </div>
                        </div>
                    </td>
                    <td>{{ emp.user.email }}</td>
                    <td>
                        <span class="badge badge-success">Active</span>
                    </td>
                    <td>
                        <a href="{% url 'employee_detail' emp.pk %}" class="btn btn-primary" style="padding: 6px 12px; font-size: 13px;">
                            View
                        </a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

## Testing the New Design

1. **View the modern dashboard**:
   - Update `core/views.py` to render `dashboard_modern.html`
   - Or create a new URL for testing

2. **Check responsiveness**:
   - Resize browser window
   - Test on mobile devices

3. **Verify branding**:
   - Nexteons logo appears in sidebar
   - Orange color scheme throughout
   - Consistent typography

## Customization

### Change Primary Color
In `modern.css`, update:
```css
:root {
    --primary: #YOUR_COLOR;
    --primary-light: #YOUR_LIGHT_COLOR;
    --primary-dark: #YOUR_DARK_COLOR;
}
```

### Adjust Sidebar Width
```css
:root {
    --sidebar-width: 240px; /* Change this value */
}
```

### Modify Border Radius
```css
:root {
    --radius: 8px; /* Make more or less rounded */
}
```

## Support

For questions or issues:
1. Check the CSS file for available classes
2. Refer to this guide for component examples
3. Use browser DevTools to inspect elements

## Next Steps

1. **Backup current templates** (already done in version control)
2. **Start with dashboard** - Test the modern design
3. **Migrate one module at a time** - Employees, then Leaves, then Payroll
4. **Test thoroughly** - Check all pages and features
5. **Gather feedback** - Make adjustments as needed

---

**Version**: 1.0
**Last Updated**: February 3, 2026
**Design System**: Nexteons Modern UI
