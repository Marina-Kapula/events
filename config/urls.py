from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import Group
from django.urls import URLPattern, URLResolver, include, path

from accounts.forms import EmailAuthenticationForm
from config import views

# Before `urlpatterns`: `admin.site.urls` builds its URL list when it is read.
admin.site.site_header = "AMFI Meetups"
admin.site.unregister(Group)

urlpatterns: list[URLPattern | URLResolver] = [
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm),
        name="login",
    ),
    # Public, so a stale "Log out" form just lands on the login page, with no `next`.
    path(
        "accounts/logout/",
        login_not_required(auth_views.LogoutView.as_view()),
        name="logout",
    ),
    path(
        "accounts/password_change/",
        auth_views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path(
        "accounts/password_reset/",
        auth_views.PasswordResetView.as_view(
            extra_email_context={"site_url": settings.SITE_URL}
        ),
        name="password_reset",
    ),
    path(
        "accounts/password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("admin/", admin.site.urls),
    path("", include("events.urls")),
    path("", include("accounts.urls")),
    path("media/<path:path>", views.media, name="media"),
]
