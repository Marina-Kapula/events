from django.urls import URLPattern, path

from events import views

urlpatterns: list[URLPattern] = [
    path("", views.event_list, name="home"),
    path("events/new/", views.event_new, name="event_new"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
]
