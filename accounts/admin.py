from typing import override

from django.contrib import admin
from django.http import HttpRequest

from accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin[User]):
    list_display = ("email", "full_name", "nationality", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff")
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
        "date_joined",
        "deleted_at",
    )
    readonly_fields = ("date_joined", "deleted_at")

    @override
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
