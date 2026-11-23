from datetime import timedelta
from typing import override

import segno
from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString, mark_safe

from accounts.models import RegistrationWindow, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin[User]):
    list_display = (
        "email",
        "full_name",
        "nationality",
        "is_active",
        "is_staff",
        "registration_window",
    )
    list_filter = ("is_active", "is_staff", "registration_window")
    search_fields = ("email", "full_name")
    ordering = ("email",)
    fields = (
        "email",
        "full_name",
        "photo",
        "nationality",
        "age",
        "gender",
        "is_active",
        "is_staff",
        "registration_window",
        "date_joined",
        "deleted_at",
    )
    readonly_fields = ("registration_window", "date_joined", "deleted_at")

    @override
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


class OpenWindowForm(forms.ModelForm[RegistrationWindow]):
    duration = forms.TypedChoiceField(
        choices=(
            (15, "15 minutes"),
            (30, "30 minutes"),
            (60, "1 hour"),
            (120, "2 hours"),
        ),
        coerce=int,
        initial=30,
        help_text="The QR code stops working after this time.",
    )

    class Meta:
        model = RegistrationWindow
        fields: tuple[str, ...] = ()  # the duration isn't a model field


class StudentInline(admin.TabularInline[User, RegistrationWindow]):
    model = User
    fields = ("full_name", "email", "nationality", "is_active")
    extra = 0
    verbose_name_plural = "Students who registered"


@admin.register(RegistrationWindow)
class RegistrationWindowAdmin(admin.ModelAdmin[RegistrationWindow]):
    form = OpenWindowForm
    list_display = ("__str__", "opened_by", "expires_at", "is_open_now")
    actions = ("close_now",)

    @override
    def get_fields(
        self, request: HttpRequest, obj: RegistrationWindow | None = None
    ) -> tuple[str, ...]:
        if obj is None:  # the add page asks only for the duration
            return ("duration",)
        return (
            "qr_code",
            "register_url",
            "expires_at",
            "is_open_now",
            "closed_at",
            "opened_by",
            "opened_at",
        )

    @override
    def get_inlines(
        self, request: HttpRequest, obj: RegistrationWindow | None
    ) -> tuple[type[StudentInline], ...]:
        return () if obj is None else (StudentInline,)

    # A window can't be edited: its page only shows it.
    @override
    def has_change_permission(
        self, request: HttpRequest, obj: RegistrationWindow | None = None
    ) -> bool:
        return False

    @override
    def save_model(
        self,
        request: HttpRequest,
        obj: RegistrationWindow,
        form: forms.ModelForm[RegistrationWindow],
        change: bool,
    ) -> None:
        assert isinstance(request.user, User)  # the admin requires a login
        obj.opened_by = request.user
        minutes: int = form.cleaned_data["duration"]
        obj.expires_at = obj.opened_at + timedelta(minutes=minutes)
        super().save_model(request, obj, form, change)

    @override
    def response_post_save_add(
        self, request: HttpRequest, obj: RegistrationWindow
    ) -> HttpResponseRedirect:
        # Straight to the QR code, instead of the list.
        url = reverse("admin:accounts_registrationwindow_change", args=(obj.pk,))
        return HttpResponseRedirect(url)

    @admin.display(description="Registration link")
    def register_url(self, window: RegistrationWindow) -> str:
        return settings.SITE_URL + reverse("register", args=(window.code,))

    @admin.display(description="QR code")
    def qr_code(self, window: RegistrationWindow) -> SafeString:
        qr = segno.make_qr(self.register_url(window))
        # Safe: segno draws the SVG from our own URL; nothing in it comes from a user.
        return mark_safe(qr.svg_inline(scale=10, light="white"))

    @admin.display(description="Open", boolean=True)
    def is_open_now(self, window: RegistrationWindow) -> bool:
        return window.is_open(now=timezone.now())

    @admin.action(description="Close now")
    def close_now(
        self, request: HttpRequest, queryset: QuerySet[RegistrationWindow]
    ) -> None:
        now = timezone.now()
        closed = queryset.filter(closed_at=None, expires_at__gt=now).update(
            closed_at=now
        )
        self.message_user(request, f"Closed {closed} window(s).")
