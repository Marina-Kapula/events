from django.urls import URLPattern, path

from events import views

urlpatterns: list[URLPattern] = [
    path("", views.event_list, name="home"),
    path("my-events/", views.my_events, name="my_events"),
    path("events/new/", views.event_new, name="event_new"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/cancel/", views.event_cancel, name="event_cancel"),
    path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("events/<int:pk>/join/", views.event_join, name="event_join"),
    path("events/<int:pk>/leave/", views.event_leave, name="event_leave"),
    path("events/<int:pk>/comments/", views.comment_add, name="comment_add"),
    path("notifications/", views.notification_list, name="notifications"),
]
