from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'), 
    path('upload-target/', views.upload_target, name='upload_target'),
    path('management/register/', views.target_registration, name='target_registration'),
    path('management/targets/', views.target_management, name='target_management'),
    path('target/<int:pk>/', views.target_detail, name='target_detail'),   
    path("register/", views.register, name="register"),
    #account management URLS
    path("login/", views.login_view, name="login"),
    path("logout/", views.log_out_view, name="logout"),
    path('accounts/manage/', views.account_manage, name='account_manage'),
    path('accounts/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('accounts/toggle-role/<int:user_id>/', views.toggle_admin_role, name='toggle_admin_role'),
    # Password Reset URLs
    path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),   
]