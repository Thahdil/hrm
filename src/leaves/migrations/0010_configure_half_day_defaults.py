from django.db import migrations

def configure_half_day(apps, schema_editor):
    LeaveType = apps.get_model('leaves', 'LeaveType')
    
    # Enable Half Day for specific leave types
    # Updating based on standard requirements: Sick, Emergency, Normal usually allow half days
    LeaveType.objects.filter(name__icontains='Sick').update(allow_half_day=True)
    LeaveType.objects.filter(name__icontains='Emergency').update(allow_half_day=True)
    LeaveType.objects.filter(name__icontains='Normal').update(allow_half_day=True)
    
    # Explicitly Disable Half Day for Annual Leave (as per project requirements)
    LeaveType.objects.filter(name__icontains='Annual').update(allow_half_day=False)

def reverse_func(apps, schema_editor):
    # No reverse operation needed strictly, but good practice to have the function
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('leaves', '0009_leaverequest_half_day_leaverequest_half_day_session_and_more'),
    ]

    operations = [
        migrations.RunPython(configure_half_day, reverse_func),
    ]
