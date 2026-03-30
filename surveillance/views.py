from django.contrib import messages
from django.shortcuts import redirect, render
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db import models
from datetime import timedelta
from .forms import UserRegistrationForm, LoginForm
from .models import TargetPerson

# Helper to check if user has admin privileges
def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='Admin').exists())

@login_required
def dashboard(request):
    # Only show targets that haven't expired or don't have an expiration date
    now = timezone.now()
    targets = TargetPerson.objects.filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
    )
    
    return render(request, 'surveillance/dashboard.html', {
        'targets': targets, 
        'is_admin': is_admin(request.user)
    })

@login_required
def home(request):
    return render(request, 'surveillance/home.html', {
        'is_admin': is_admin(request.user)
    })

@login_required
@user_passes_test(is_admin, login_url='home')
def upload_target(request):
    if request.method == 'POST' and request.FILES.get('image'):
        name = request.POST.get('name')
        image = request.FILES.get('image')
        duration = request.POST.get('duration') # Captured from the dropdown
        
        expires_at = None
        now = timezone.now()

        # Logic for standardized TTL choices
        if duration == "1h":
            expires_at = now + timedelta(hours=1)
        elif duration == "12h":
            expires_at = now + timedelta(hours=12)
        elif duration == "1d":
            expires_at = now + timedelta(days=1)
        elif duration == "7d":
            expires_at = now + timedelta(days=7)
        elif duration == "custom":
            custom_date = request.POST.get('custom_date')
            if custom_date:
                # Converts the string from datetime-local input to a Python datetime object
                expires_at = timezone.make_aware(timezone.datetime.fromisoformat(custom_date))

        TargetPerson.objects.create(
            name=name, 
            image=image, 
            expires_at=expires_at
        )
        
        messages.success(request, f"Target '{name}' authorized successfully.")
        return redirect('dashboard')
    
    messages.error(request, "Failed to upload target.")
    return redirect('dashboard')

# ... (rest of your registration/login/logout views)
def register(request):
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.set_password(user_form.cleaned_data['password'])
            new_user.save()
            messages.success(request, 'Profile Initialized!')
            return redirect("login")
    else:
        user_form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'user_form': user_form})

def login_view(request):
    if request.user.is_authenticated: return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data.get('identifier')
            password = form.cleaned_data.get('password')
            user_obj = User.objects.filter(email=identifier).first()
            username = user_obj.username if user_obj else identifier
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, 'Access Granted.')
                return redirect('home') 
            else:
                messages.error(request, 'Invalid Credentials.')
    else:
        form = LoginForm()
    return render(request, 'registration/login.html', {'form': form})

def log_out_view(request):
    logout(request)
    messages.info(request, "Session Terminated.")
    return redirect("login")