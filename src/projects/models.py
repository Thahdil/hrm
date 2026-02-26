from django.db import models
from django.conf import settings

class Project(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assigned_employees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='assigned_projects', blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class ProjectHours(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_hours')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='hours')
    date = models.DateField()
    
    # Core Data Points
    standard_hours = models.DecimalField(max_digits=4, decimal_places=2, help_text="Max 8.0 per day")
    extra_time = models.DecimalField(max_digits=4, decimal_places=2, default=0.0)
    overtime = models.DecimalField(max_digits=4, decimal_places=2, default=0.0)
    
    task_description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Project Hours"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.employee} - {self.project} - {self.date}"
