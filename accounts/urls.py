from django.urls import URLPattern, path

from accounts import views

urlpatterns: list[URLPattern] = [
    path("register/<str:code>/", views.register, name="register"),
]
