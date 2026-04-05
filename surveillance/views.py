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
from django.utils.translation import gettext as _
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.core.mail import send_mail
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .forms import UserRegistrationForm, LoginForm, TargetPersonForm, UserUpdateForm
from .models import TargetPerson, SecurityProfile, DetectionEvent, TargetAssignment, Notification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_admin(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'admin')


def is_privileged_staff(user):
    return user.is_authenticated and (
        user.is_superuser or
        (hasattr(user, 'profile') and user.profile.role in ['admin', 'supervisor'])
    )


def _push_notification(recipient, notification_type, title, message, assignment=None):
    """
    Creates a Notification DB record and pushes it to the user's personal
    WebSocket group so they see it in real-time without a page refresh.
    Also sends an email if the user has an email address.
    """
    notif = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        related_assignment=assignment,
    )

    # In-app WebSocket push
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{recipient.id}",
        {
            "type": "send_notification",
            "notification_id": notif.id,
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "created_at": notif.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    # Email notification
    if recipient.email:
        try:
            send_mail(
                subject=f"[Butterfly] {title}",
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@butterfly.local'),
                recipient_list=[recipient.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"[Notification] Email send error: {e}")

    return notif


# ---------------------------------------------------------------------------
# Core pages
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    now = timezone.now()
    targets = TargetPerson.objects.filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
    )
    # Last 20 detection events for the "recent activity" panel
    recent_events = DetectionEvent.objects.select_related('matched_target').order_by('-timestamp')[:20]

    return render(request, 'surveillance/dashboard.html', {
        'targets': targets,
        'is_admin': is_admin(request.user),
        'recent_events': recent_events,
    })


@login_required
def home(request):
    unread_count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return render(request, 'surveillance/home.html', {
        'is_admin': is_admin(request.user),
        'unread_count': unread_count,
    })


# ---------------------------------------------------------------------------
# Target management — SCOPED BY ROLE
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def target_management(request):
    user = request.user
    base_qs = TargetPerson.objects.all().order_by('-id')

    if is_admin(user):
        # Admin sees every target
        targets = base_qs
    else:
        # Supervisor sees only targets they personally uploaded
        targets = base_qs.filter(uploaded_by=user)

    return render(request, 'surveillance/target_management.html', {
        'targets': targets,
        'is_admin': is_admin(user),
    })


@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def target_registration(request):
    if request.method == 'POST':
        return upload_target(request)
    form = TargetPersonForm()
    return render(request, 'surveillance/target_management_registration.html', {
        'form': form,
        'is_admin': True,
    })


@login_required
@user_passes_test(is_admin, login_url='target_management')
def target_detail(request, pk):
    target = get_object_or_404(TargetPerson, pk=pk)
    assignments = TargetAssignment.objects.filter(target=target).select_related(
        'assigned_to', 'assigned_by'
    ).order_by('-created_at')
    operators = User.objects.filter(profile__role='operator').select_related('profile')
    return render(request, 'surveillance/target_management_details.html', {
        'target': target,
        'assignments': assignments,
        'operators': operators,
        'is_admin': is_admin(request.user),
    })

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def upload_target(request):
    if request.method == 'POST':
        form = TargetPersonForm(request.POST, request.FILES)
        if form.is_valid():
            target = form.save(commit=False)

            # Record who uploaded this target
            target.uploaded_by = request.user

            # Expiration logic
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
                        target.expires_at = timezone.make_aware(
                            timezone.datetime.fromisoformat(custom_date)
                        )
                    except ValueError:
                        pass

            target.save()
            messages.success(request, f"Subject '{target.name}' successfully enrolled.")
            return redirect('target_management')
        else:
            for field, errors in form.errors.items():
                messages.error(request, f"{field}: {errors[0]}")
            return render(request, 'surveillance/target_management_registration.html', {
                'form': form,
                'is_admin': True,
            })

    return redirect('target_registration')


# ---------------------------------------------------------------------------
# Assign target to operator
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def assign_target(request, target_pk):
    """
    POST-only view.  Admin or supervisor assigns a target to a chosen operator.
    Payload: { operator_id: <int>, note: <str> }
    """
    if request.method != 'POST':
        return redirect('target_management')

    target = get_object_or_404(TargetPerson, pk=target_pk)
    operator_id = request.POST.get('operator_id')
    note = request.POST.get('note', '')

    operator = get_object_or_404(User, pk=operator_id)

    # Supervisor can only assign targets they uploaded
    if not is_admin(request.user) and target.uploaded_by != request.user:
        messages.error(request, "You can only assign targets you uploaded.")
        return redirect('target_management')

    assignment = TargetAssignment.objects.create(
        target=target,
        assigned_by=request.user,
        assigned_to=operator,
        note=note,
        status='pending',
    )

    _push_notification(
        recipient=operator,
        notification_type='assignment',
        title=f"New target assigned: {target.name}",
        message=(
            f"You have been assigned to monitor '{target.name} {target.last_name}'.\n"
            f"Assigned by: {request.user.get_full_name() or request.user.username}\n"
            f"Note: {note or 'None'}"
        ),
        assignment=assignment,
    )

    messages.success(request, f"Target '{target.name}' assigned to {operator.username}.")
    return redirect('target_management')


@login_required
def pass_back_target(request, assignment_pk):
    """
    Operator marks an assignment as 'passed_back', notifying the original uploader.
    """
    assignment = get_object_or_404(TargetAssignment, pk=assignment_pk, assigned_to=request.user)
    assignment.status = 'passed_back'
    assignment.save()

    uploader = assignment.target.uploaded_by
    if uploader:
        _push_notification(
            recipient=uploader,
            notification_type='pass_back',
            title=f"Update on target: {assignment.target.name}",
            message=(
                f"Operator {request.user.username} has passed back the target "
                f"'{assignment.target.name} {assignment.target.last_name}'.\n"
                f"Assignment ID: #{assignment.pk}"
            ),
            assignment=assignment,
        )

    messages.success(request, "Target passed back to the original uploader.")
    return redirect('operator_assignments')


@login_required
def operator_assignments(request):
    """
    View for operators to see all targets assigned to them.
    Admins and supervisors can also see this page for their own assignments.
    """
    assignments = TargetAssignment.objects.filter(
        assigned_to=request.user
    ).select_related('target', 'assigned_by').order_by('-created_at')

    return render(request, 'surveillance/operator_assignments.html', {
        'assignments': assignments,
        'is_admin': is_admin(request.user),
    })


@login_required
def acknowledge_assignment(request, assignment_pk):
    """Operator acknowledges they have seen and accepted the assignment."""
    assignment = get_object_or_404(TargetAssignment, pk=assignment_pk, assigned_to=request.user)
    assignment.status = 'acknowledged'
    assignment.save()
    return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@login_required
def notifications_list(request):
    notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:50]
    # Mark all as read when the user opens the page
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return render(request, 'surveillance/notifications.html', {
        'notifications': notifs,
        'is_admin': is_admin(request.user),
    })


@login_required
def unread_notification_count(request):
    """JSON endpoint polled by the navbar badge."""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'count': count})


# ---------------------------------------------------------------------------
# Detection history
# ---------------------------------------------------------------------------

@login_required
def detection_history(request):
    events = DetectionEvent.objects.select_related('matched_target').order_by('-timestamp')
    paginator = Paginator(events, 30)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'surveillance/detection_history.html', {
        'page_obj': page,
        'is_admin': is_admin(request.user),
    })


# ---------------------------------------------------------------------------
# User / account management (unchanged from original, kept for completeness)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_admin, login_url='home')
def account_manage(request):
    query = request.GET.get('q', '')
    sort_type = request.GET.get('sort', '-date_joined')

    users_list = User.objects.select_related('profile').filter(
        models.Q(username__icontains=query) |
        models.Q(email__icontains=query)
    )

    sort_map = {
        'name_asc': 'username',
        'name_desc': '-username',
        'date_old': 'date_joined',
        'date_new': '-date_joined',
        'rank_admin': ['-is_staff', 'username'],
        'rank_obs': ['is_staff', 'username'],
        'role_supervisor': ['-profile__role', 'username'],
        'role_operator': ['profile__role', 'username'],
    }

    order = sort_map.get(sort_type, '-date_joined')
    if isinstance(order, list):
        users_list = users_list.order_by(*order)
    else:
        users_list = users_list.order_by(order)

    paginator = Paginator(users_list, 6)
    users = paginator.get_page(request.GET.get('page'))
    is_filtered = bool(query or sort_type not in ['-date_joined', 'date_new'])

    return render(request, 'surveillance/account_manage.html', {
        'users': users,
        'query': query,
        'current_sort': sort_type,
        'is_admin': True,
        'is_filtered': is_filtered,
    })


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


@login_required
@user_passes_test(is_admin, login_url='home')
def toggle_admin_role(request, user_id):
    user_to_mod = get_object_or_404(User, id=user_id)
    admin_group, _ = Group.objects.get_or_create(name='Admin')
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


def register(request):
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST, request.FILES)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.set_password(user_form.cleaned_data['password'])
            new_user.save()
            SecurityProfile.objects.create(
                user=new_user,
                badge_number=user_form.cleaned_data['badge_number'],
                profile_picture=user_form.cleaned_data.get('profile_picture'),
                role=user_form.cleaned_data['role'],
                emergency_contact=user_form.cleaned_data['emergency_contact'],
            )
            messages.success(request, f'Security Profile for {new_user.username} Initialized!')
            return redirect("login")
    else:
        user_form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'user_form': user_form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
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


@login_required
def account_detail(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if not request.user.is_superuser and request.user.id != target_user.id:
        raise PermissionDenied("You do not have permission to view this profile.")
    return render(request, 'surveillance/account_manage_details.html', {
        'target_user': target_user,
        'profile': target_user.profile,
    })


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

    return render(request, 'surveillance/account_update.html', {
        'form': form,
        'target_user': target_user,
        'profile': profile,
    })