from django.db import models
from django.conf import settings

class Meeting(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organized_meetings'
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='meetings'
    )
    room = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f"{self.title} ({self.start_time})"

    @property
    def duration_hours(self):
        diff = self.end_time - self.start_time
        return diff.total_seconds() / 3600
