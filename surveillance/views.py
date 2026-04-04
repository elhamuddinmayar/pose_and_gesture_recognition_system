from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db import models
from datetime import timedelta
from django.core.paginator import Paginator 
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _ # Added for the _() function
from django.contrib.admin.views.decorators import staff_member_required # Added this

# Note: SecurityProfile is a MODEL, not a form. Remove it from your .forms import line
from .forms import UserRegistrationForm, LoginForm, TargetPersonForm, UserUpdateForm
from .models import TargetPerson, SecurityProfile


# Helper to check if user has admin privileges
def is_admin(user):
    if not user.is_authenticated:
        return False
    # Check if they are a Django Superuser OR if their profile role is 'admin'
    return user.is_superuser or user.profile.role == 'admin'

@login_required
def dashboard(request):
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

def is_privileged_staff(user):
    return user.is_authenticated and (user.profile.role in ['admin', 'supervisor'] or user.is_superuser)

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def target_management(request):
    targets = TargetPerson.objects.all().order_by('-id') 
    return render(request, 'surveillance/target_management.html', {
        'targets': targets,
        'is_admin': True
    })

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def target_registration(request):
    """View to render the full registration page and handle logic"""
    if request.method == 'POST':
        # We process the data using the upload_target logic
        return upload_target(request) 
    
    # CRITICAL: You must initialize and pass the form here
    form = TargetPersonForm() 
    
    return render(request, 'surveillance/target_management_registration.html', {
        'form': form,  # Added this line so your HTML can see the fields
        'is_admin': True
    })
    
    
#....... targer person.....

#target person details 
@login_required
@user_passes_test(is_admin, login_url='target_management')
def target_detail(request, pk):
    target = get_object_or_404(TargetPerson, pk=pk)
    return render(request, 'surveillance/target_management_details.html', {
        'target': target,
        'is_admin': True
    })

#uploading ther target person info to system 
@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def upload_target(request):
    if request.method == 'POST':
        # 1. Initialize the form with POST data and FILES
        form = TargetPersonForm(request.POST, request.FILES)
        
        if form.is_valid():
            # 2. Save the form but don't commit to DB yet so we can add expires_at
            target = form.save(commit=False)
            
            # 3. Handle the Expiration Logic (Duration)
            duration = request.POST.get('duration')
            now = timezone.now()
            durations = {
                "1h": timedelta(hours=1),
                "12h": timedelta(hours=12),
                "1d": timedelta(days=1),
                "7d": timedelta(days=7),
            }

            if duration in durations:
                target.expires_at = now + durations[duration]
            elif duration == "custom":
                custom_date = request.POST.get('custom_date')
                if custom_date:
                    try:
                        target.expires_at = timezone.make_aware(timezone.datetime.fromisoformat(custom_date))
                    except ValueError:
                        pass
            
            # 4. Final Save
            target.save()
            messages.success(request, f"Subject '{target.name}' successfully enrolled.")
            return redirect('target_management')
        else:
            # If form is invalid, show the specific errors
            for field, errors in form.errors.items():
                messages.error(request, f"{field}: {errors[0]}")
            
            # Return to registration page with the invalid form to show errors
            return render(request, 'surveillance/target_management_registration.html', {
                'form': form,
                'is_admin': True
            })

    return redirect('target_registration')

#...................... Controlling Users By Admin .........................
@login_required
@user_passes_test(is_admin, login_url='home')
def account_manage(request):
    query = request.GET.get('q', '')
    sort_type = request.GET.get('sort', '-date_joined')

    # Base Queryset - Added select_related for performance when sorting by profile roles
    users_list = User.objects.select_related('profile').filter(
        models.Q(username__icontains=query) | 
        models.Q(email__icontains=query)
    )

    # Sorting Logic (Old rules preserved + New Rank properties added)
    sort_map = {
        # --- Original Rules ---
        'name_asc': 'username',
        'name_desc': '-username',
        'date_old': 'date_joined',
        'date_new': '-date_joined',
        'rank_admin': ['-is_staff', 'username'],
        'rank_obs': ['is_staff', 'username'],
        
        # --- New Tactical Rank Properties ---
        # Sorts by the 'role' field in your SecurityProfile model
        'role_supervisor': ['-profile__role', 'username'], # Supervisors usually sort to top alphabetically
        'role_operator': ['profile__role', 'username'],   # Operators sort to bottom/top based on string
    }
    
    order = sort_map.get(sort_type, '-date_joined')
    if isinstance(order, list):
        users_list = users_list.order_by(*order)
    else:
        users_list = users_list.order_by(order)

    # Pagination
    paginator = Paginator(users_list, 6) 
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)

    is_filtered = bool(query or sort_type not in ['-date_joined', 'date_new'])

    return render(request, 'surveillance/account_manage.html', {
        'users': users,
        'query': query,
        'current_sort': sort_type,
        'is_admin': True,
        'is_filtered': is_filtered
    })
    
        
#deletation of system users
@login_required
@user_passes_test(is_admin, login_url='home')
def delete_user(request, user_id):
    if request.user.id == user_id:
        messages.error(request, "CRITICAL: You cannot terminate your own access.")
        return redirect('account_manage')
        
    user_to_delete = get_object_or_404(User, id=user_id)
    username = user_to_delete.username
    user_to_delete.delete()
    messages.success(request, f"User '{username}' has been removed from the system.")
    return redirect('account_manage')


#handle user role like admin or sub admin
@login_required
@user_passes_test(is_admin, login_url='home')
def toggle_admin_role(request, user_id):
    user_to_mod = get_object_or_404(User, id=user_id)
    admin_group, created = Group.objects.get_or_create(name='Admin')

    if user_to_mod.groups.filter(name='Admin').exists():
        user_to_mod.groups.remove(admin_group)
        user_to_mod.is_staff = False 
        messages.info(request, f"Access Level: Observer - {user_to_mod.username}")
    else:
        user_to_mod.groups.add(admin_group)
        user_to_mod.is_staff = True
        messages.success(request, f"Access Level: Admin - {user_to_mod.username}")
    
    user_to_mod.save()
    return redirect('account_manage')


#................   Auth system control part................
#User registration 
def register(request):
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST, request.FILES) 
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.set_password(user_form.cleaned_data['password'])
            new_user.save()

            # Link the profile
            SecurityProfile.objects.create(
                user=new_user,
                badge_number=user_form.cleaned_data['badge_number'],
                profile_picture=user_form.cleaned_data.get('profile_picture'),
                role=user_form.cleaned_data['role'],
                emergency_contact=user_form.cleaned_data['emergency_contact']
            )

            messages.success(request, f'Security Profile for {new_user.username} Initialized!')
            return redirect("login")
    else:
        user_form = UserRegistrationForm()
    
    return render(request, 'registration/register.html', {'user_form': user_form})
#user login
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
#user log out
def log_out_view(request):
    logout(request)
    messages.info(request, "Session Terminated.")
    return redirect("login")


@login_required
def account_detail(request, user_id):
    # Fetch the user being requested
    target_user = get_object_or_404(User, id=user_id)
    
    # Logic: Only Admin can see others. Non-admins can ONLY see their own ID.
    if not request.user.is_superuser and request.user.id != target_user.id:
        raise PermissionDenied("You do not have permission to view this profile.")

    return render(request, 'surveillance/account_manage_details.html', {
        'target_user': target_user,
        'profile': target_user.profile # Accessing the SecurityProfile model
    })
    
# views.py

@staff_member_required
def account_update(request, pk):
    target_user = get_object_or_404(User, id=pk)
    profile = target_user.profile

    if request.method == 'POST':
        form = UserUpdateForm(request.POST, request.FILES, instance=target_user)
        if form.is_valid():
            form.save()
            
            profile.badge_number = form.cleaned_data['badge_number']
            profile.role = form.cleaned_data['role']
            profile.emergency_contact = form.cleaned_data['emergency_contact']
            
            if form.cleaned_data.get('profile_picture'):
                profile.profile_picture = form.cleaned_data['profile_picture']
            
            profile.save()
            messages.success(request, _("Profile updated successfully."))
            return redirect('account_detail', user_id=target_user.id)
    else:
        initial_data = {
            'badge_number': profile.badge_number,
            'role': profile.role,
            'emergency_contact': profile.emergency_contact,
        }
        form = UserUpdateForm(instance=target_user, initial=initial_data)

    # Add 'profile': profile to the dictionary below:
    return render(request, 'surveillance/account_update.html', {
        'form': form, 
        'target_user': target_user, 
        'profile': profile  # <--- THIS IS THE MISSING KEY
    })