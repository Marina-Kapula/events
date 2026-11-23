from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from events.forms import EventFilterForm, EventForm
from events.models import Event, Size
from events.services import event_create


def event_list(request: HttpRequest) -> HttpResponse:
    form = EventFilterForm(request.GET)
    events = Event.objects.listed(now=timezone.now())
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            events = events.search(data["q"])
        if data["city"]:
            events = events.in_city(data["city"])
        if data["date"]:
            events = events.on_date(day=data["date"])
        if data["type"]:
            events = events.of_type(data["type"])
        if data["size"]:
            events = events.of_size(Size(data["size"]))
    return render(request, "events/event_list.html", {"form": form, "events": events})


def event_detail(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User):
        raise Http404
    event = get_object_or_404(
        Event.objects.visible_to(user).select_related("organizer"), pk=pk
    )
    return render(request, "events/event_detail.html", {"event": event})


def event_new(request: HttpRequest) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event_create(event=form.save(commit=False), organizer=user)
            messages.success(
                request, "Sent to AMFI for review. We'll email you when it's approved."
            )
            return redirect("home")
    else:
        form = EventForm()
    return render(request, "events/event_form.html", {"form": form})
