from django.urls import URLPattern, path

from accounts import views

urlpatterns: list[URLPattern] = [
    path("register/<str:code>/", views.register, name="register"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("profile/", views.profile_edit, name="profile_edit"),
]
