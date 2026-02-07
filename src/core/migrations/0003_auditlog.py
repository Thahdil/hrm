# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0002_publicholiday_companysettings_work_friday_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('CREATE', 'Created'), ('UPDATE', 'Updated'), ('DELETE', 'Deleted'), ('LOGIN', 'Logged In'), ('LOGOUT', 'Logged Out'), ('APPROVE', 'Approved'), ('REJECT', 'Rejected'), ('EXPORT', 'Exported'), ('IMPORT', 'Imported'), ('VIEW', 'Viewed')], max_length=20)),
                ('module', models.CharField(choices=[('PAYROLL', 'Payroll'), ('ATTENDANCE', 'Attendance'), ('LEAVES', 'Leaves'), ('EMPLOYEES', 'Employees'), ('USERS', 'Users'), ('DOCUMENTS', 'Documents'), ('TICKETS', 'Air Tickets'), ('SYSTEM', 'System'), ('OTHER', 'Other')], default='OTHER', max_length=20)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('object_repr', models.CharField(blank=True, help_text='String representation of the object', max_length=200)),
                ('changes', models.JSONField(blank=True, help_text='What changed (old_value/new_value)', null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.contenttype')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['-timestamp'], name='core_auditl_timesta_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['user', '-timestamp'], name='core_auditl_user_id_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['action', '-timestamp'], name='core_auditl_action_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['module', '-timestamp'], name='core_auditl_module_idx'),
        ),
    ]
