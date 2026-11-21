from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import Group
from django.urls import URLPattern, URLResolver, path

from accounts.forms import EmailAuthenticationForm
from config import views

# Before `urlpatterns`: `admin.site.urls` builds its URL list when it is read.
admin.site.site_header = "AMFI Meetups"
admin.site.unregister(Group)

urlpatterns: list[URLPattern | URLResolver] = [
    path("", views.home, name="home"),
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
    path("admin/", admin.site.urls),
]
