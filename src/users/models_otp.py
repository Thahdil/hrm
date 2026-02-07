from django.db import models
from django.conf import settings
from django.utils import timezone
import random

class OTPToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        # Valid for 10 minutes
        now = timezone.now()
        return not self.is_used and (now - self.created_at).total_seconds() < 600

    @staticmethod
    def generate(user):
        # Invalidate old tokens
        OTPToken.objects.filter(user=user, is_used=False).update(is_used=True)
        # Create new one
        token = f"{random.randint(100000, 999999)}"
        return OTPToken.objects.create(user=user, token=token)
