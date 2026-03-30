from django.contrib import admin
from .models import TargetPerson

@admin.register(TargetPerson)
class TargetPersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')