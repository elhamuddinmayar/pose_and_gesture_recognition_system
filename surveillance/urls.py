from django.urls import path
from . import views

urlpatterns = [
    # Core pages
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Auth
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.log_out_view, name='logout'),

    # Target management
    path('targets/', views.target_management, name='target_management'),
    path('targets/register/', views.target_registration, name='target_registration'),
    path('targets/<int:pk>/', views.target_detail, name='target_detail'),

    # Assignment
    path('targets/<int:target_pk>/assign/', views.assign_target, name='assign_target'),
    path('assignments/', views.operator_assignments, name='operator_assignments'),
    path('assignments/<int:assignment_pk>/acknowledge/', views.acknowledge_assignment, name='acknowledge_assignment'),
    path('assignments/<int:assignment_pk>/pass-back/', views.pass_back_target, name='pass_back_target'),

    # Detection history
    path('history/', views.detection_history, name='detection_history'),

    # Notifications
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/count/', views.unread_notification_count, name='unread_notification_count'),

    # Account management
    path('accounts/', views.account_manage, name='account_manage'),
    path('accounts/<int:user_id>/', views.account_detail, name='account_detail'),
    path('accounts/<int:pk>/update/', views.account_update, name='account_update'),
    path('accounts/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('accounts/<int:user_id>/toggle-role/', views.toggle_admin_role, name='toggle_admin_role'),
]