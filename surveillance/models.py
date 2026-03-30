from django.db import models
from django.utils import timezone
import os

class TargetPerson(models.Model):
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to='targets/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # --- TTL Fields ---
    is_found = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        # Standard way to clean up files when model is deleted
        if self.image:
            if os.path.isfile(self.image.path):
                os.remove(self.image.path)
        super().delete(*args, **kwargs)