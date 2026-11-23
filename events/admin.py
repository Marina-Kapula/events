from typing import ClassVar, override

from django import forms
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from accounts.models import User
from config.photos import PhotoField
from events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin[Event]):
    list_display = ("title", "organizer", "starts_at", "status")
    list_filter = ("status", "type")
    search_fields = ("title", "city")
    list_select_related = ("organizer",)
    # They change only through the review buttons, which call services (SPEC §6.2).
    readonly_fields = ("status", "organizer")
    # Photos uploaded in the admin are checked and shrunk too (SPEC.md §6.8).
    formfield_overrides: ClassVar = {models.ImageField: {"form_class": PhotoField}}

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
