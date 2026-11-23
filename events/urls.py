from django.urls import URLPattern, path

from events import views

urlpatterns: list[URLPattern] = [
    path("events/new/", views.event_new, name="event_new"),
]
