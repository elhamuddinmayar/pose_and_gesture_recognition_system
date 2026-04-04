from django.db import models
from django.utils import timezone
import os
from django.db import models
from django.contrib.auth.models import User

class SecurityProfile(models.Model):
    ROLE_CHOICES = [
        ('operator', 'Surveillance Operator'),
        ('supervisor', 'Shift Supervisor'),
        ('admin', 'System Administrator'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profiles/security/', default='profiles/default.png')
    badge_number = models.CharField(max_length=20, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='operator')
    emergency_contact = models.CharField(max_length=100)
    is_on_duty = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.badge_number} - {self.user.username}"
    
    
class TargetPerson(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    MARITAL_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Divorced', 'Divorced'),
        ('Widowed', 'Widowed'),
    ]
    
    #Basic Biometrics 
    name = models.CharField(max_length=100) # First Name
    last_name = models.CharField(max_length=100, default='N/A')
    father_name = models.CharField(max_length=100, default='N/A')
    image = models.ImageField(upload_to='targets/')
    
    #Personal Details 
    # Note: IntegerFields use numbers, not strings
    age = models.IntegerField(default=0) 
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    place_of_birth = models.CharField(max_length=255, default='N/A')
    marital_status = models.CharField(max_length=20, choices=MARITAL_CHOICES, default='Single')
    job = models.CharField(max_length=100, default='N/A')
    
    # --- Identification & Contact ---
    # For unique fields, it's better to allow null than to set a shared default string
    tazkira_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, default='0000000000')
    address = models.TextField(default='N/A')
    
    # --- Criminal Record ---
    crime = models.CharField(max_length=255, default='None') 
    description = models.TextField(blank=True, default='') 
    
    # --- System / TTL Fields ---
    created_at = models.DateTimeField(auto_now_add=True)
    is_found = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} {self.last_name} ({self.tazkira_number})"

    def delete(self, *args, **kwargs):
        # Standard way to clean up files when model is deleted
        if self.image:
            try:
                if os.path.isfile(self.image.path):
                    os.remove(self.image.path)
            except Exception:
                pass # Path might not exist
        super().delete(*args, **kwargs)