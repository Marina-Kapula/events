from django.urls import URLPattern, path

from accounts import views

urlpatterns: list[URLPattern] = [
    # Before register/<code>/, or "sent" would be taken for a code.
    path("register/sent/", views.register_sent, name="register_sent"),
    path("register/<str:code>/", views.register, name="register"),
    path("verify/<str:uidb64>/<str:token>/", views.verify, name="verify"),
    path(
        "accounts/resend-verification/",
        views.resend_verification,
        name="resend_verification",
    ),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("profile/", views.profile_edit, name="profile_edit"),
]
