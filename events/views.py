from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.models import User
from events.forms import EventForm
from events.services import event_create


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
