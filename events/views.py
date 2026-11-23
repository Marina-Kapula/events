from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from events.forms import EventFilterForm, EventForm
from events.models import Event, Participation, Size
from events.services import event_create, participation_join, participation_leave


def event_list(request: HttpRequest) -> HttpResponse:
    form = EventFilterForm(request.GET)
    events = Event.objects.listed(now=timezone.now()).with_going_count()
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
    participations = list(
        Participation.objects.filter(event=event).select_related("user")
    )
    going = [p for p in participations if p.status == Participation.Status.GOING]
    mine = next((p for p in participations if p.user == user), None)
    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "going": going,
            "spots_taken": 1 + len(going),
            "waiting_count": len(participations) - len(going),
            "mine": mine,
            "is_full": 1 + len(going) >= event.max_people,
            "is_open": event.status == Event.Status.APPROVED
            and event.starts_at > timezone.now(),
        },
    )


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


@require_POST
def event_join(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    event = get_object_or_404(Event.objects.visible_to(user), pk=pk)
    try:
        participation = participation_join(event=event, user=user, now=timezone.now())
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if participation.status == Participation.Status.GOING:
            messages.success(request, "You're going. See you there!")
        else:
            messages.success(
                request,
                "The event is full: you're on the waiting list. "
                "We'll email you if a spot frees up.",
            )
    return redirect("event_detail", pk=event.pk)


@require_POST
def event_leave(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    event = get_object_or_404(Event.objects.visible_to(user), pk=pk)
    try:
        participation_leave(event=event, user=user, now=timezone.now())
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "You left the event.")
    return redirect("event_detail", pk=event.pk)
