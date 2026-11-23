from django.urls import URLPattern, path

from events import views

urlpatterns: list[URLPattern] = [
    path("", views.event_list, name="home"),
    path("events/new/", views.event_new, name="event_new"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/join/", views.event_join, name="event_join"),
    path("events/<int:pk>/leave/", views.event_leave, name="event_leave"),
]
