from typing import ClassVar, override

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils import timezone

from accounts.models import User
from config.photos import PhotoField
from events.models import Event, EventChange
from events.services import (
    event_approve,
    event_cancel,
    event_change_approve,
    event_change_reject,
    event_reject,
)


class EventChangeInline(admin.StackedInline[EventChange, Event]):
    """The organizer's proposed changes, read only: use the buttons below."""

    model = EventChange

    @override
    def has_add_permission(self, request: HttpRequest, obj: Event | None) -> bool:
        return False

    @override
    def has_change_permission(
        self, request: HttpRequest, obj: Event | None = None
    ) -> bool:
        return False

    @override
    def has_delete_permission(
        self, request: HttpRequest, obj: Event | None = None
    ) -> bool:
        return False


@admin.register(Event)
class EventAdmin(admin.ModelAdmin[Event]):
    list_display = ("title", "organizer", "starts_at", "status", "changes_pending")
    list_filter = ("status", "type")
    search_fields = ("title", "city")
    list_select_related = ("organizer", "change")
    inlines = (EventChangeInline,)
    # They change only through the review buttons, which call services (SPEC §6.2).
    readonly_fields = ("status", "organizer")
    # Photos uploaded in the admin are checked and shrunk too (SPEC.md §6.8).
    formfield_overrides: ClassVar = {models.ImageField: {"form_class": PhotoField}}
    # Our template adds the review buttons under the form.
    change_form_template = "admin/events/event/change_form.html"

    @admin.display(boolean=True)
    def changes_pending(self, obj: Event) -> bool:
        return hasattr(obj, "change")

    @override
    def save_model(
        self,
        request: HttpRequest,
        obj: Event,
        form: forms.ModelForm[Event],
        change: bool,
    ) -> None:
        if not change:
            # An event added by staff is approved at once, with them as organizer.
            assert isinstance(request.user, User)  # the admin requires a login
            obj.organizer = request.user
            obj.status = Event.Status.APPROVED
        super().save_model(request, obj, form, change)

    @override
    def response_change(self, request: HttpRequest, obj: Event) -> HttpResponse:
        # Runs after the form is saved. A review button sends its name with the form.
        try:
            if "_approve" in request.POST:
                event_approve(event=obj, now=timezone.now())
                self.message_user(request, "Approved. The organizer has been emailed.")
            elif "_reject" in request.POST:
                event_reject(event=obj, reason=obj.review_note)
                self.message_user(request, "Rejected. The organizer has been emailed.")
            elif "_approve_changes" in request.POST:
                event_change_approve(event=obj, now=timezone.now())
                self.message_user(
                    request, "Changes approved. Everyone on the event was emailed."
                )
            elif "_reject_changes" in request.POST:
                event_change_reject(event=obj, reason=obj.review_note)
                self.message_user(
                    request, "Changes rejected. The organizer was emailed."
                )
            elif "_cancel" in request.POST:
                assert isinstance(request.user, User)  # the admin requires a login
                event_cancel(event=obj, by=request.user, now=timezone.now())
                self.message_user(
                    request, "Cancelled. Everyone going or waiting was emailed."
                )
            else:
                return super().response_change(request, obj)
        except ValidationError as error:
            self.message_user(request, " ".join(error.messages), messages.ERROR)
        # Back to the same page, which now shows the new status.
        return HttpResponseRedirect(request.path)
